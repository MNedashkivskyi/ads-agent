"""Unit tests for Task 6.4 — Stripe billing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adcopilot.domain.entities import PlanTier, User, UserId

_USER_ID = UserId(str(uuid.uuid4()))


def _make_user(
    subscription_status: str = "trialing",
    stripe_customer_id: str | None = None,
    plan: PlanTier = PlanTier.STARTER,
) -> User:
    return User(
        id=_USER_ID,
        email="test@example.com",
        telegram_chat_id=111222333,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        plan=plan,
        subscription_status=subscription_status,
        stripe_customer_id=stripe_customer_id,
    )


# ---------------------------------------------------------------------------
# Webhook dispatch: _handle_stripe_event routes to correct handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_stripe_event_dispatches_subscription_created() -> None:
    from adcopilot.config import Settings
    from adcopilot.interfaces.api.billing import _handle_stripe_event

    settings = Settings(DATABASE_URL="postgresql+asyncpg://x:x@localhost/x")
    event = {
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_abc",
                "customer": "cus_abc",
                "status": "trialing",
                "trial_end": None,
            }
        },
    }

    with patch(
        "adcopilot.interfaces.api.billing._handle_subscription_event",
        new_callable=AsyncMock,
    ) as mock_handler:
        await _handle_stripe_event(event, settings)

    mock_handler.assert_awaited_once_with(
        "customer.subscription.created",
        event["data"]["object"],
        settings,
    )


@pytest.mark.asyncio
async def test_handle_stripe_event_dispatches_payment_failed() -> None:
    from adcopilot.config import Settings
    from adcopilot.interfaces.api.billing import _handle_stripe_event

    settings = Settings(DATABASE_URL="postgresql+asyncpg://x:x@localhost/x")
    event = {
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_xyz", "id": "inv_xyz"}},
    }

    with patch(
        "adcopilot.interfaces.api.billing._handle_payment_failed",
        new_callable=AsyncMock,
    ) as mock_handler:
        await _handle_stripe_event(event, settings)

    mock_handler.assert_awaited_once_with(event["data"]["object"], settings)


@pytest.mark.asyncio
async def test_handle_stripe_event_ignores_unknown_events() -> None:
    from adcopilot.config import Settings
    from adcopilot.interfaces.api.billing import _handle_stripe_event

    settings = Settings(DATABASE_URL="postgresql+asyncpg://x:x@localhost/x")
    event = {"type": "charge.succeeded", "data": {"object": {}}}

    # Should not raise
    await _handle_stripe_event(event, settings)


# ---------------------------------------------------------------------------
# Inactive statuses constant
# ---------------------------------------------------------------------------


def test_inactive_statuses_are_defined() -> None:
    from adcopilot.interfaces.api.billing import _INACTIVE_STATUSES

    assert "past_due" in _INACTIVE_STATUSES
    assert "canceled" in _INACTIVE_STATUSES
    assert "unpaid" in _INACTIVE_STATUSES
    assert "trialing" not in _INACTIVE_STATUSES
    assert "active" not in _INACTIVE_STATUSES


# ---------------------------------------------------------------------------
# Plan enforcement: 402 when account limit exceeded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oauth_callback_enforces_starter_account_limit() -> None:
    """OAuth callback returns 402 when STARTER user already has 1 account."""
    from fastapi import HTTPException

    from adcopilot.interfaces.api.oauth import oauth_google_callback

    starter_user = _make_user(plan=PlanTier.STARTER)
    existing_account = MagicMock()

    mock_user_repo = MagicMock()
    mock_user_repo.get_by_id = AsyncMock(return_value=starter_user)

    mock_acc_repo = MagicMock()
    mock_acc_repo.list_for_user = AsyncMock(return_value=[existing_account])

    mock_session = AsyncMock()

    mock_http_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "refresh_token": "rt",
        "access_token": "at",
        "expires_in": 3600,
    }
    mock_http_client.post = AsyncMock(return_value=mock_response)

    mock_ads_client = MagicMock()
    mock_ads_client.list_accessible_customers = AsyncMock(return_value=["123-456-7890"])

    with (
        patch(
            "adcopilot.interfaces.api.oauth.consume_state_jwt",
            return_value=str(_USER_ID),
        ),
        patch("adcopilot.interfaces.api.oauth.SqlUserRepository", return_value=mock_user_repo),
        patch(
            "adcopilot.interfaces.api.oauth.SqlGoogleAdsAccountRepository",
            return_value=mock_acc_repo,
        ),
        patch("adcopilot.interfaces.api.oauth.SqlOAuthCredentialsRepository", MagicMock()),
        patch("adcopilot.interfaces.api.oauth.httpx.AsyncClient") as mock_http_cls,
        patch(
            "adcopilot.infrastructure.google_ads.client.GoogleAdsClientAdapter",
            return_value=mock_ads_client,
        ),
    ):
        http_ctx = AsyncMock()
        http_ctx.__aenter__ = AsyncMock(return_value=mock_http_client)
        http_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_http_cls.return_value = http_ctx

        from adcopilot.config import Settings

        settings = Settings(
            DATABASE_URL="postgresql+asyncpg://x:x@localhost/x",
            GOOGLE_ADS_CLIENT_ID="cid",
            GOOGLE_ADS_CLIENT_SECRET="csec",
        )

        with pytest.raises(HTTPException) as exc_info:
            await oauth_google_callback(
                code="auth_code",
                state="state_jwt",
                settings=settings,
                session=mock_session,
                redis_client=MagicMock(),
            )

    assert exc_info.value.status_code == 402


@pytest.mark.asyncio
async def test_oauth_callback_allows_growth_second_account() -> None:
    """GROWTH plan (limit=3) allows linking when 1 account already exists."""
    from adcopilot.interfaces.api.oauth import oauth_google_callback

    growth_user = _make_user(plan=PlanTier.GROWTH)
    existing_account = MagicMock()

    mock_user_repo = MagicMock()
    mock_user_repo.get_by_id = AsyncMock(return_value=growth_user)

    mock_acc_repo = MagicMock()
    mock_acc_repo.list_for_user = AsyncMock(return_value=[existing_account])  # 1 of 3 limit
    mock_acc_repo.save = AsyncMock()

    mock_creds_repo = MagicMock()
    mock_creds_repo.save = AsyncMock()

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    mock_http_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "refresh_token": "rt",
        "access_token": "at",
        "expires_in": 3600,
    }
    mock_http_client.post = AsyncMock(return_value=mock_response)

    mock_ads_client = MagicMock()
    mock_ads_client.list_accessible_customers = AsyncMock(return_value=["123-456-7890"])

    with (
        patch(
            "adcopilot.interfaces.api.oauth.consume_state_jwt",
            return_value=str(_USER_ID),
        ),
        patch("adcopilot.interfaces.api.oauth.SqlUserRepository", return_value=mock_user_repo),
        patch(
            "adcopilot.interfaces.api.oauth.SqlGoogleAdsAccountRepository",
            return_value=mock_acc_repo,
        ),
        patch(
            "adcopilot.interfaces.api.oauth.SqlOAuthCredentialsRepository",
            return_value=mock_creds_repo,
        ),
        patch("adcopilot.interfaces.api.oauth.httpx.AsyncClient") as mock_http_cls,
        patch(
            "adcopilot.infrastructure.google_ads.client.GoogleAdsClientAdapter",
            return_value=mock_ads_client,
        ),
    ):
        http_ctx = AsyncMock()
        http_ctx.__aenter__ = AsyncMock(return_value=mock_http_client)
        http_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_http_cls.return_value = http_ctx

        from adcopilot.config import Settings

        settings = Settings(
            DATABASE_URL="postgresql+asyncpg://x:x@localhost/x",
            GOOGLE_ADS_CLIENT_ID="cid",
            GOOGLE_ADS_CLIENT_SECRET="csec",
        )

        result = await oauth_google_callback(
            code="auth_code",
            state="state_jwt",
            settings=settings,
            session=mock_session,
            redis_client=MagicMock(),
        )

    assert "linked_customer_ids" in result


# ---------------------------------------------------------------------------
# Trial reminder: selects users in 2-day window
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trial_reminders_sends_to_ending_trials() -> None:
    """_run_trial_reminders sends message to users whose trial ends in ~2 days."""
    from adcopilot.config import Settings
    from adcopilot.interfaces.worker.tasks import _run_trial_reminders

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://x:x@localhost/x",
        TELEGRAM_BOT_TOKEN="bot:token",
    )

    mock_user_model = MagicMock()
    mock_user_model.telegram_chat_id = 999
    mock_user_model.subscription_status = "trialing"
    mock_user_model.trial_ends_at = datetime.now(UTC) + timedelta(days=2)
    mock_user_model.id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_user_model]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.begin = MagicMock(return_value=mock_session)

    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()

    mock_bot_instance = AsyncMock()
    mock_bot_instance.__aenter__ = AsyncMock(return_value=mock_bot_instance)
    mock_bot_instance.__aexit__ = AsyncMock(return_value=False)
    mock_bot_instance.send_message = AsyncMock()

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
        patch("sqlalchemy.ext.asyncio.AsyncSession", return_value=mock_session),
        patch("telegram.Bot", return_value=mock_bot_instance),
    ):
        result = await _run_trial_reminders(settings)

    assert result["sent"] == 1
    assert result["skipped"] == 0
    mock_bot_instance.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_trial_reminders_skips_when_no_bot_token() -> None:
    from adcopilot.config import Settings
    from adcopilot.interfaces.worker.tasks import _run_trial_reminders

    settings = Settings(DATABASE_URL="postgresql+asyncpg://x:x@localhost/x")
    result = await _run_trial_reminders(settings)
    assert result["reason"] == "no_bot_token"
