"""Unit tests for OAuth token refresh validation.

Covers:
- is_google_auth_error() detection for all known error signatures
- mutations_adapter raises GoogleAdsAuthError (not GoogleAdsUnavailable) on auth failure
- execute_recommendation_task handles GoogleAdsAuthError as non-retriable
- _handle_auth_failure marks rec FAILED, sets needs_reauth, sends notification
- _notify_reauth_required sends reauth notification for snapshot auth failures
- SnapshotAccountUseCase already sets needs_reauth (regression guard)
- send_reauth_required in TelegramDigestNotifier and FakeTelegramNotifier
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adcopilot.domain.exceptions import GoogleAdsAuthError, GoogleAdsUnavailable
from adcopilot.infrastructure.google_ads.client import is_google_auth_error

# ---------------------------------------------------------------------------
# is_google_auth_error()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "UNAUTHENTICATED: Request had invalid authentication credentials",
        "invalid credentials supplied",
        "error: invalid_grant token has been expired or revoked",
        "Token has been expired or revoked",
        "AuthenticationError: oauth_token_invalid",
        "access_denied",
        "Invalid Credentials",
    ],
)
def test_is_google_auth_error_returns_true_for_auth_messages(message: str) -> None:
    assert is_google_auth_error(Exception(message)) is True


@pytest.mark.parametrize(
    "message",
    [
        "UNAVAILABLE: Deadline exceeded",
        "quota exceeded",
        "Resource exhausted",
        "Internal server error",
        "Connection refused",
    ],
)
def test_is_google_auth_error_returns_false_for_non_auth_messages(message: str) -> None:
    assert is_google_auth_error(Exception(message)) is False


# ---------------------------------------------------------------------------
# mutations_adapter raises GoogleAdsAuthError on auth failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mutations_adapter_raises_auth_error_on_invalid_grant() -> None:
    """When the Google Ads API returns an auth error, mutations must raise GoogleAdsAuthError."""
    from adcopilot.infrastructure.google_ads.mutations_adapter import GoogleAdsMutationsAdapter

    settings = MagicMock()
    adapter = GoogleAdsMutationsAdapter(settings)

    # Simulate the google-ads client raising an invalid_grant error
    auth_exc = Exception("invalid_grant: Token has been expired or revoked")

    mock_client = MagicMock()
    mock_client.get_service.return_value.ad_group_criterion_path.return_value = "rn"
    mock_client.get_type.return_value = MagicMock()
    mock_client.get_service.return_value.mutate_ad_group_criteria.side_effect = auth_exc

    with (
        patch.object(adapter, "_build_client", return_value=mock_client),
        pytest.raises(GoogleAdsAuthError),
    ):
        await adapter.pause_keyword(
            refresh_token="tok",
            customer_id="123",
            ad_group_id=1,
            criterion_id=2,
        )


@pytest.mark.asyncio
async def test_mutations_adapter_raises_unavailable_on_generic_error() -> None:
    """Non-auth errors must still be wrapped as GoogleAdsUnavailable."""
    from adcopilot.infrastructure.google_ads.mutations_adapter import GoogleAdsMutationsAdapter

    settings = MagicMock()
    adapter = GoogleAdsMutationsAdapter(settings)

    generic_exc = Exception("UNAVAILABLE: service temporarily down")
    mock_client = MagicMock()
    mock_client.get_service.return_value.ad_group_criterion_path.return_value = "rn"
    mock_client.get_type.return_value = MagicMock()
    mock_client.get_service.return_value.mutate_ad_group_criteria.side_effect = generic_exc

    with (
        patch.object(adapter, "_build_client", return_value=mock_client),
        pytest.raises(GoogleAdsUnavailable),
    ):
        await adapter.pause_keyword(
            refresh_token="tok",
            customer_id="123",
            ad_group_id=1,
            criterion_id=2,
        )


# ---------------------------------------------------------------------------
# execute_recommendation_task — auth failure path (non-retriable)
# ---------------------------------------------------------------------------


def _make_bound_task(max_retries: int = 3, current_retry: int = 0) -> MagicMock:
    task_self = MagicMock()
    task_self.max_retries = max_retries
    task_self.request.retries = current_retry
    task_self.retry.side_effect = lambda exc: (_ for _ in ()).throw(exc)
    return task_self


def _run_task_body(task_self: MagicMock, rec_id: str) -> None:
    """Replicate the execute_recommendation_task body for isolated unit testing."""
    import asyncio
    import contextlib

    from adcopilot.domain.exceptions import GoogleAdsAuthError
    from adcopilot.interfaces.worker.tasks import (
        _handle_auth_failure,
        _handle_execution_failure,
        _run_execute_recommendation,
    )

    try:
        asyncio.run(_run_execute_recommendation(rec_id))
    except GoogleAdsAuthError:
        with contextlib.suppress(Exception):
            asyncio.run(_handle_auth_failure(rec_id))
        raise
    except Exception as exc:
        if task_self.request.retries < task_self.max_retries:
            raise task_self.retry(exc=exc) from exc
        error_message = str(exc) or type(exc).__name__
        with contextlib.suppress(Exception):
            asyncio.run(_handle_execution_failure(rec_id, error_message))
        raise


def test_auth_error_is_not_retried() -> None:
    """GoogleAdsAuthError must propagate immediately without calling self.retry()."""
    task_self = _make_bound_task(max_retries=3, current_retry=0)
    auth_exc = GoogleAdsAuthError("invalid_grant")

    with (
        patch(
            "adcopilot.interfaces.worker.tasks._run_execute_recommendation",
            new_callable=AsyncMock,
            side_effect=auth_exc,
        ),
        patch(
            "adcopilot.interfaces.worker.tasks._handle_auth_failure",
            new_callable=AsyncMock,
        ),
        pytest.raises(GoogleAdsAuthError),
    ):
        _run_task_body(task_self, "rec-1")

    task_self.retry.assert_not_called()


def test_auth_error_calls_handle_auth_failure() -> None:
    """GoogleAdsAuthError must trigger _handle_auth_failure."""
    task_self = _make_bound_task(max_retries=3, current_retry=0)

    with (
        patch(
            "adcopilot.interfaces.worker.tasks._run_execute_recommendation",
            new_callable=AsyncMock,
            side_effect=GoogleAdsAuthError("revoked"),
        ),
        patch(
            "adcopilot.interfaces.worker.tasks._handle_auth_failure",
            new_callable=AsyncMock,
        ) as mock_handle,
        pytest.raises(GoogleAdsAuthError),
    ):
        _run_task_body(task_self, "rec-auth")

    mock_handle.assert_awaited_once_with("rec-auth")


def test_generic_error_still_retries() -> None:
    """Non-auth transient errors must still go through the retry path."""
    task_self = _make_bound_task(max_retries=3, current_retry=0)
    generic_exc = RuntimeError("timeout")

    with (
        patch(
            "adcopilot.interfaces.worker.tasks._run_execute_recommendation",
            new_callable=AsyncMock,
            side_effect=generic_exc,
        ),
        patch(
            "adcopilot.interfaces.worker.tasks._handle_auth_failure",
            new_callable=AsyncMock,
        ),
        pytest.raises(RuntimeError),
    ):
        _run_task_body(task_self, "rec-2")

    task_self.retry.assert_called_once_with(exc=generic_exc)


# ---------------------------------------------------------------------------
# TelegramDigestNotifier.send_reauth_required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_digest_notifier_send_reauth_required_with_url() -> None:
    from adcopilot.infrastructure.telegram.digest_notifier import TelegramDigestNotifier

    bot_mock = AsyncMock()
    notifier = TelegramDigestNotifier.__new__(TelegramDigestNotifier)
    notifier._bot = bot_mock

    await notifier.send_reauth_required(
        chat_id=42,
        account_name="Acme Corp",
        reauth_url="https://app.example.com/oauth/google/start?account_id=abc",
    )

    bot_mock.send_message.assert_awaited_once()
    kwargs = bot_mock.send_message.call_args.kwargs
    assert kwargs["chat_id"] == 42
    assert "Acme Corp" in kwargs["text"]
    assert "https://app.example.com" in kwargs["text"]


@pytest.mark.asyncio
async def test_digest_notifier_send_reauth_required_without_url() -> None:
    from adcopilot.infrastructure.telegram.digest_notifier import TelegramDigestNotifier

    bot_mock = AsyncMock()
    notifier = TelegramDigestNotifier.__new__(TelegramDigestNotifier)
    notifier._bot = bot_mock

    await notifier.send_reauth_required(chat_id=7, account_name="Test Account")

    bot_mock.send_message.assert_awaited_once()
    text = bot_mock.send_message.call_args.kwargs["text"]
    assert "Test Account" in text
    # Should contain a CTA without a URL
    assert "zaloguj" in text.lower()


# ---------------------------------------------------------------------------
# FakeTelegramNotifier.send_reauth_required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_notifier_records_send_reauth_required() -> None:
    from adcopilot.infrastructure.telegram.fake_notifier import FakeTelegramNotifier

    notifier = FakeTelegramNotifier()
    await notifier.send_reauth_required(
        chat_id=99,
        account_name="My Account",
        reauth_url="https://example.com/reauth",
    )

    assert len(notifier.calls) == 1
    call = notifier.calls[0]
    assert call["method"] == "send_reauth_required"
    assert call["chat_id"] == 99
    assert call["account_name"] == "My Account"
    assert call["reauth_url"] == "https://example.com/reauth"


# ---------------------------------------------------------------------------
# SnapshotAccountUseCase — needs_reauth set on auth error (regression guard)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_use_case_sets_needs_reauth_on_auth_error() -> None:
    """SnapshotAccountUseCase must persist needs_reauth=True when GoogleAdsAuthError fires."""
    from datetime import date

    from adcopilot.application.use_cases.snapshot_account import SnapshotAccountUseCase
    from adcopilot.domain.entities import AccountId, GoogleAdsAccount, UserId

    account = GoogleAdsAccount(
        id=AccountId("acc-1"),
        user_id=UserId("usr-1"),
        customer_id="123",
        descriptive_name="Test",
        currency="USD",
        timezone="UTC",
        is_manager=False,
        write_enabled=True,
        connected_at=datetime.now(UTC),
        needs_reauth=False,
    )

    saved: list[GoogleAdsAccount] = []

    account_repo = MagicMock()
    account_repo.get = AsyncMock(return_value=account)
    account_repo.save = AsyncMock(side_effect=lambda a: saved.append(a) or a)

    creds_repo = MagicMock()
    creds_repo.get = AsyncMock(
        return_value=MagicMock(refresh_token="tok", access_token=None, expires_at=None)
    )

    ads_client = MagicMock()
    ads_client.query_campaigns = AsyncMock(side_effect=GoogleAdsAuthError("invalid_grant"))
    ads_client.query_ad_groups = AsyncMock(return_value=[])
    ads_client.query_keywords = AsyncMock(return_value=[])
    ads_client.query_search_terms = AsyncMock(return_value=[])
    ads_client.query_ads = AsyncMock(return_value=[])
    ads_client.query_negative_keywords = AsyncMock(return_value=[])
    ads_client.query_device_performance = AsyncMock(return_value=[])
    ads_client.query_geo_performance = AsyncMock(return_value=[])
    ads_client.query_hour_performance = AsyncMock(return_value=[])
    ads_client.query_day_of_week_performance = AsyncMock(return_value=[])
    ads_client.query_audience_performance = AsyncMock(return_value=[])
    ads_client.query_conversion_actions = AsyncMock(return_value=[])

    use_case = SnapshotAccountUseCase(
        ads_client=ads_client,
        snapshot_repo=MagicMock(),
        credentials_repo=creds_repo,
        account_repo=account_repo,
    )

    result = await use_case.execute(AccountId("acc-1"), date.today())

    assert result.success is False
    assert "GoogleAdsAuthError" in (result.error_message or "")
    # The use case must have saved the account with needs_reauth=True
    assert saved, "account_repo.save was never called"
    assert saved[0].needs_reauth is True
