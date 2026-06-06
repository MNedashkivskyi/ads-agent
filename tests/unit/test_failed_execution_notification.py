"""Unit tests for failed-execution notification flow."""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adcopilot.infrastructure.fake_notifier import FakeNotifier

# ---------------------------------------------------------------------------
# FakeNotifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_notifier_records_send_execution_failed() -> None:
    from datetime import datetime

    from adcopilot.domain.entities import AccountId
    from adcopilot.domain.recommendation import (
        Recommendation,
        RecommendationId,
        RecommendationKind,
        RecommendationSeverity,
        RecommendationStatus,
    )

    rec = Recommendation(
        id=RecommendationId("rec-1"),
        account_id=AccountId("acc-1"),
        kind=RecommendationKind.PAUSE_KEYWORD,
        severity=RecommendationSeverity.HIGH,
        target={},
        payload={},
        estimated_monthly_savings_micros=0,
        evidence={},
        created_at=datetime.utcnow(),
        status=RecommendationStatus.FAILED,
    )

    notifier = FakeNotifier()
    await notifier.send_execution_failed(chat_id=42, recommendation=rec, error_message="boom")

    assert len(notifier.calls) == 1
    call = notifier.calls[0]
    assert call["method"] == "send_execution_failed"
    assert call["chat_id"] == 42
    assert call["recommendation"] is rec
    assert call["error_message"] == "boom"


# ---------------------------------------------------------------------------
# TelegramDigestNotifier.send_execution_failed
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# execute_recommendation_task — task configuration
# ---------------------------------------------------------------------------


def test_execute_recommendation_task_is_bound_with_correct_retry_config() -> None:
    """The Celery task must be configured with bind=True and 3 max retries."""
    from adcopilot.interfaces.worker.tasks import execute_recommendation_task

    assert execute_recommendation_task.max_retries == 3
    assert execute_recommendation_task.name == (
        "adcopilot.interfaces.worker.tasks.execute_recommendation_task"
    )


# ---------------------------------------------------------------------------
# execute_recommendation_task — failure path (tested via the run function)
# ---------------------------------------------------------------------------


def _make_bound_task(max_retries: int = 3, current_retry: int = 3) -> MagicMock:
    """Return a mock that matches what Celery passes as `self` in bind=True tasks."""
    task_self = MagicMock()
    task_self.max_retries = max_retries
    task_self.request.retries = current_retry

    def _retry_side_effect(exc: BaseException) -> None:
        raise exc from exc

    task_self.retry.side_effect = _retry_side_effect
    return task_self


def _run_task(task_self: MagicMock, rec_id: str) -> None:
    """Call execute_recommendation_task's body directly, bypassing Celery overhead."""
    import asyncio

    from adcopilot.interfaces.worker.tasks import (
        _handle_execution_failure,
        _run_execute_recommendation,
    )

    # Replicate the task body so we can inject mocks via patch in tests
    try:
        asyncio.run(_run_execute_recommendation(rec_id))
    except Exception as exc:
        if task_self.request.retries < task_self.max_retries:
            raise task_self.retry(exc=exc) from exc
        error_message = str(exc) or type(exc).__name__
        with contextlib.suppress(Exception):
            asyncio.run(_handle_execution_failure(rec_id, error_message))
        raise


def test_execute_recommendation_task_retries_on_transient_error() -> None:
    """When retries are not exhausted, retry() should be called and the exc raised."""
    task_self = _make_bound_task(max_retries=3, current_retry=0)
    exc = RuntimeError("transient error")

    with (
        patch(
            "adcopilot.interfaces.worker.tasks._run_execute_recommendation",
            new_callable=AsyncMock,
            side_effect=exc,
        ),
        pytest.raises(RuntimeError, match="transient error"),
    ):
        _run_task(task_self, "rec-abc")

    task_self.retry.assert_called_once_with(exc=exc)


def test_execute_recommendation_task_calls_handle_failure_when_retries_exhausted() -> None:
    """After max retries, _handle_execution_failure is called with the right args."""
    task_self = _make_bound_task(max_retries=3, current_retry=3)
    exc = RuntimeError("permanent failure")

    with (
        patch(
            "adcopilot.interfaces.worker.tasks._run_execute_recommendation",
            new_callable=AsyncMock,
            side_effect=exc,
        ),
        patch(
            "adcopilot.interfaces.worker.tasks._handle_execution_failure",
            new_callable=AsyncMock,
        ) as mock_handle,
        pytest.raises(RuntimeError, match="permanent failure"),
    ):
        _run_task(task_self, "rec-abc")

    mock_handle.assert_awaited_once_with("rec-abc", "permanent failure")


def test_execute_recommendation_task_campaign_removed_expires_without_raising() -> None:
    """A removed campaign is an expected terminal condition: the task expires the
    stale rec(s) and returns cleanly instead of raising (which would log a
    misleading traceback and trip the task_failure/Sentry path)."""
    from adcopilot.domain.exceptions import CampaignNotFoundError
    from adcopilot.interfaces.worker.tasks import execute_recommendation_task

    exc = CampaignNotFoundError("Campaign 123 no longer exists or has been removed.")

    with (
        patch(
            "adcopilot.interfaces.worker.tasks._run_execute_recommendation",
            new_callable=AsyncMock,
            side_effect=exc,
        ),
        patch(
            "adcopilot.interfaces.worker.tasks._expire_recs_for_removed_campaign",
            new_callable=AsyncMock,
            return_value=2,
        ) as mock_expire,
    ):
        result = execute_recommendation_task.apply(args=["rec-removed"])

    assert result.successful()  # no exception propagated
    assert result.result["status"] == "expired"
    assert result.result["expired"] == 2
    assert "no longer exists" in result.result["reason"]
    mock_expire.assert_awaited_once_with("rec-removed")


@pytest.mark.asyncio
async def test_handle_execution_failure_sends_web_notification() -> None:
    """ADW-002: a failed execution marks the rec FAILED and notifies the user."""
    from adcopilot.interfaces.worker.tasks import _handle_execution_failure

    class _FakeSession:
        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *_a: object) -> bool:
            return False

        def begin(self) -> object:
            session = self

            class _Ctx:
                async def __aenter__(self_) -> "_FakeSession":
                    return session

                async def __aexit__(self_, *_a: object) -> bool:
                    return False

            return _Ctx()

    rec = MagicMock()
    rec.account_id = "acc-1"
    rec.kind.value = "PAUSE_KEYWORD"
    account = MagicMock()
    account.user_id = "user-7"

    rec_repo = MagicMock()
    rec_repo.get = AsyncMock(return_value=rec)
    rec_repo.update_status = AsyncMock()
    acc_repo = MagicMock()
    acc_repo.get = AsyncMock(return_value=account)
    notifier = MagicMock()
    notifier.send_execution_result = AsyncMock()

    engine = MagicMock()
    engine.dispose = AsyncMock()

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine),
        patch("sqlalchemy.ext.asyncio.AsyncSession", return_value=_FakeSession()),
        patch(
            "adcopilot.infrastructure.db.repositories.recommendation_repository.SqlRecommendationRepository",
            return_value=rec_repo,
        ),
        patch(
            "adcopilot.infrastructure.db.repositories.google_ads_account_repository.SqlGoogleAdsAccountRepository",
            return_value=acc_repo,
        ),
        patch(
            "adcopilot.infrastructure.notifications.web_notifier_adapter.SqlWebNotifier",
            return_value=notifier,
        ),
    ):
        await _handle_execution_failure("rec-1", "boom")

    from adcopilot.domain.recommendation import RecommendationStatus

    rec_repo.update_status.assert_awaited_once()
    assert rec_repo.update_status.await_args.args[1] == RecommendationStatus.FAILED
    notifier.send_execution_result.assert_awaited_once()
    kwargs = notifier.send_execution_result.await_args.kwargs
    assert kwargs["user_id"] == "user-7"
    assert kwargs["metadata"]["action"] == "execution_failed"
    # Polish, user-facing, no raw error leak.
    assert "boom" not in kwargs["body"]


def test_execute_recommendation_task_handle_failure_exception_is_swallowed() -> None:
    """If _handle_execution_failure raises, the original exc is still propagated."""
    task_self = _make_bound_task(max_retries=3, current_retry=3)
    exc = ValueError("original")

    with (
        patch(
            "adcopilot.interfaces.worker.tasks._run_execute_recommendation",
            new_callable=AsyncMock,
            side_effect=exc,
        ),
        patch(
            "adcopilot.interfaces.worker.tasks._handle_execution_failure",
            new_callable=AsyncMock,
            side_effect=RuntimeError("handle failure blew up"),
        ),
        pytest.raises(ValueError, match="original"),
    ):
        _run_task(task_self, "rec-abc")
