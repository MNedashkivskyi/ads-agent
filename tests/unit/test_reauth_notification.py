"""Unit tests for REAUTH_REQUIRED notifications.

Covers the shared message builder and the snapshot use case's "notify only on
the first transition into needs_reauth" dedup rule, so repeated nightly auth
failures don't spam the user's notification bell.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from adcopilot.application.services.reauth_notification import (
    REAUTH_NOTIFICATION_TITLE,
    build_reauth_notification,
)
from adcopilot.application.use_cases.snapshot_account import SnapshotAccountUseCase
from adcopilot.domain.entities import AccountId, GoogleAdsAccount, UserId


def _account(*, needs_reauth: bool, descriptive_name: str = "Acme Sp. z o.o.") -> GoogleAdsAccount:
    return GoogleAdsAccount(
        id=AccountId("acc-1"),
        user_id=UserId("user-1"),
        customer_id="1234567890",
        descriptive_name=descriptive_name,
        currency="PLN",
        timezone="Europe/Warsaw",
        is_manager=False,
        write_enabled=True,
        needs_reauth=needs_reauth,
        connected_at=datetime.now(UTC),
    )


def test_builder_uses_descriptive_name_and_polish_title() -> None:
    title, body, metadata = build_reauth_notification(_account(needs_reauth=False))
    assert title == REAUTH_NOTIFICATION_TITLE
    assert "Acme Sp. z o.o." in body
    assert "Reauth" in body
    assert metadata == {"account_id": "acc-1", "customer_id": "1234567890"}


def test_builder_falls_back_to_customer_id_when_no_name() -> None:
    _title, body, _metadata = build_reauth_notification(
        _account(needs_reauth=False, descriptive_name="")
    )
    assert "ID 1234567890" in body


@pytest.mark.asyncio
async def test_snapshot_notifies_on_first_transition() -> None:
    """A healthy account hitting an auth error notifies exactly once."""
    account_repo = AsyncMock()
    web_notifier = AsyncMock()
    use_case = SnapshotAccountUseCase(
        ads_client=AsyncMock(),
        snapshot_repo=AsyncMock(),
        credentials_repo=AsyncMock(),
        account_repo=account_repo,
        web_notifier=web_notifier,
    )

    await use_case._mark_needs_reauth(_account(needs_reauth=False))

    account_repo.save.assert_awaited_once()
    saved = account_repo.save.await_args.args[0]
    assert saved.needs_reauth is True
    web_notifier.send_reauth_required.assert_awaited_once()
    assert web_notifier.send_reauth_required.await_args.kwargs["user_id"] == "user-1"


@pytest.mark.asyncio
async def test_snapshot_does_not_renotify_when_already_flagged() -> None:
    """An account already needing reauth must not re-notify on the next failure."""
    web_notifier = AsyncMock()
    use_case = SnapshotAccountUseCase(
        ads_client=AsyncMock(),
        snapshot_repo=AsyncMock(),
        credentials_repo=AsyncMock(),
        account_repo=AsyncMock(),
        web_notifier=web_notifier,
    )

    await use_case._mark_needs_reauth(_account(needs_reauth=True))

    web_notifier.send_reauth_required.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshot_without_notifier_still_flags() -> None:
    """Backward-compat: no notifier injected → still flags, no crash."""
    account_repo = AsyncMock()
    use_case = SnapshotAccountUseCase(
        ads_client=AsyncMock(),
        snapshot_repo=AsyncMock(),
        credentials_repo=AsyncMock(),
        account_repo=account_repo,
        web_notifier=None,
    )

    await use_case._mark_needs_reauth(_account(needs_reauth=False))

    account_repo.save.assert_awaited_once()
