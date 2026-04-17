"""Callback query handlers for immediate alert action buttons."""
from __future__ import annotations

import structlog
from telegram import Update
from telegram.ext import ContextTypes

logger = structlog.get_logger(__name__)


async def alert_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Route alert action button presses."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    data: str = query.data or ""

    if data.startswith("alert_pause:"):
        alert_id = data.split(":", 1)[1]
        await _handle_pause(query, alert_id)
    elif data.startswith("alert_investigate:"):
        account_id = data.split(":", 1)[1]
        await _handle_investigate(query, account_id)
    elif data.startswith("alert_ack:"):
        alert_id = data.split(":", 1)[1]
        await _handle_ack(query, alert_id)


async def _handle_pause(query: object, alert_id: str) -> None:
    """Pause all enabled campaigns for the account tied to this alert."""
    import uuid as _uuid

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from telegram import CallbackQuery

    from adcopilot.config import get_settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.models import AlertModel
    from adcopilot.infrastructure.db.repositories.audit_log_repository import (
        SqlAuditLogRepository,
    )
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.interfaces.worker.tasks import _pause_all_enabled_campaigns

    assert isinstance(query, CallbackQuery)
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    try:
        async with AsyncSession(engine) as session, session.begin():
            # Look up the alert to get account_id
            from sqlalchemy import select
            result = await session.execute(
                select(AlertModel).where(AlertModel.id == _uuid.UUID(alert_id))
            )
            alert_model = result.scalar_one_or_none()
            if alert_model is None:
                await query.edit_message_text("⚠️ Alert not found.")
                return

            account_id = AccountId(str(alert_model.account_id))
            account_repo = SqlGoogleAdsAccountRepository(session)
            credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)
            audit_repo = SqlAuditLogRepository(session)

            account = await account_repo.get(account_id)
            if account is None:
                await query.edit_message_text("⚠️ Account not found.")
                return

            credentials = await credentials_repo.get(account_id)
            if credentials is None:
                await query.edit_message_text("⚠️ OAuth credentials not found.")
                return

            paused = await _pause_all_enabled_campaigns(
                settings=settings,
                customer_id=account.customer_id,
                refresh_token=credentials.refresh_token,
                account_id=account_id,
                audit_repo=audit_repo,
            )

        original_text = query.message.text if query.message else ""
        await query.edit_message_text(
            f"{original_text}\n\n🛑 *{paused} campaign(s) paused.*",
            parse_mode="Markdown",
        )
        logger.info("alert_pause executed", alert_id=alert_id, paused=paused)
    except Exception as exc:
        logger.exception("alert_pause failed", alert_id=alert_id)
        await query.edit_message_text(f"⚠️ Failed to pause: {exc!s:.200}")
    finally:
        await engine.dispose()


async def _handle_investigate(query: object, account_id: str) -> None:
    """Send the user a link to the alerts dashboard for this account."""
    from telegram import CallbackQuery

    from adcopilot.config import get_settings

    assert isinstance(query, CallbackQuery)
    settings = get_settings()

    base_url = getattr(settings, "APP_URL", None) or "https://app.adcopilot.ai"
    url = f"{base_url}/app/alerts?account_id={account_id}"
    if query.message:
        await query.message.reply_text(
            f"👀 *Investigate alerts:*\n{url}",
            parse_mode="Markdown",
        )
    logger.info("alert_investigate", account_id=account_id)


async def _handle_ack(query: object, alert_id: str) -> None:
    """Mark alert acknowledged and suppress same-kind alerts for 24 h."""
    import uuid as _uuid
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from telegram import CallbackQuery

    from adcopilot.config import get_settings
    from adcopilot.domain.alert import AlertId, AlertKind
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.models import AlertModel
    from adcopilot.infrastructure.db.repositories.alert_repository import SqlAlertRepository

    assert isinstance(query, CallbackQuery)
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    try:
        async with AsyncSession(engine) as session, session.begin():
            from sqlalchemy import select
            result = await session.execute(
                select(AlertModel).where(AlertModel.id == _uuid.UUID(alert_id))
            )
            alert_model = result.scalar_one_or_none()
            if alert_model is None:
                await query.edit_message_text("⚠️ Alert not found.")
                return

            account_id = AccountId(str(alert_model.account_id))
            kind = AlertKind(alert_model.kind)
            alert_repo = SqlAlertRepository(session)

            now = datetime.now(UTC)
            await alert_repo.acknowledge(AlertId(alert_id), now)
            await alert_repo.suppress_kind(account_id, kind, now + timedelta(hours=24))

        original_text = query.message.text if query.message else ""
        await query.edit_message_text(
            f"{original_text}\n\n✓ *Acknowledged. Same alerts suppressed for 24 h.*",
            parse_mode="Markdown",
        )
        logger.info("alert_ack executed", alert_id=alert_id)
    except Exception as exc:
        logger.exception("alert_ack failed", alert_id=alert_id)
        await query.edit_message_text(f"⚠️ Failed to acknowledge: {exc!s:.200}")
    finally:
        await engine.dispose()
