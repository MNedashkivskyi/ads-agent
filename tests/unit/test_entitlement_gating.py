"""LAUNCH-015: approve/execute is gated behind an active subscription."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _user(status: str, trial_ends_at=None):
    u = MagicMock()
    u.subscription_status = status
    u.trial_ends_at = trial_ends_at
    return u


async def _run(user):
    from adcopilot.interfaces.api.users import _assert_active_subscription

    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=user)
    with patch(
        "adcopilot.infrastructure.db.repositories.user_repository.SqlUserRepository",
        return_value=repo,
    ):
        await _assert_active_subscription(MagicMock(), "user-1")


@pytest.mark.asyncio
async def test_active_passes() -> None:
    await _run(_user("active"))  # no raise


@pytest.mark.asyncio
async def test_valid_trial_passes() -> None:
    await _run(_user("trialing", datetime.now(UTC) + timedelta(days=3)))  # no raise


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["past_due", "canceled", "unpaid"])
async def test_inactive_blocked(status: str) -> None:
    with pytest.raises(HTTPException) as exc:
        await _run(_user(status))
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_expired_trial_blocked() -> None:
    with pytest.raises(HTTPException) as exc:
        await _run(_user("trialing", datetime.now(UTC) - timedelta(days=1)))
    assert exc.value.status_code == 402
