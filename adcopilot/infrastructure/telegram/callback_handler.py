"""Telegram inline-button callback handler for recommendation actions."""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from telegram import Update
from telegram.ext import ContextTypes

from adcopilot.config import get_settings

logger = structlog.get_logger(__name__)

_ACTION_LABELS = {
    "approve": "Approved",
    "decline": "Declined",
    "snooze": "Snoozed for 7 days",
}


async def recommendation_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle approve/decline/snooze inline button presses."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    parts = query.data.split(":", 1)
    if len(parts) != 2 or parts[0] not in _ACTION_LABELS:
        logger.warning("unknown callback data", data=query.data)
        return

    action, rec_id_str = parts
    telegram_chat_id = query.from_user.id if query.from_user else None
    if telegram_chat_id is None:
        return

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            from adcopilot.domain.recommendation import RecommendationId
            from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
                SqlGoogleAdsAccountRepository,
            )
            from adcopilot.infrastructure.db.repositories.recommendation_repository import (
                SqlRecommendationRepository,
            )
            from adcopilot.infrastructure.db.repositories.snooze_repository import (
                SqlSnoozeRepository,
            )

            rec_repo = SqlRecommendationRepository(session)
            account_repo = SqlGoogleAdsAccountRepository(session)

            from sqlalchemy import select

            from adcopilot.domain.entities import UserId
            from adcopilot.infrastructure.db.models import UserModel

            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id == telegram_chat_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                await query.edit_message_text("Unauthorized: Telegram account not linked.")
                return

            user_id = UserId(str(user_model.id))
            rec_id = RecommendationId(rec_id_str)
            rec = await rec_repo.get(rec_id)
            if rec is None:
                await query.edit_message_text("Recommendation not found or already acted on.")
                return

            user_accounts = await account_repo.list_for_user(user_id)
            user_account_ids = {a.id for a in user_accounts}
            if rec.account_id not in user_account_ids:
                logger.warning(
                    "unauthorized callback attempt",
                    user_id=user_id,
                    rec_id=rec_id,
                    rec_account_id=rec.account_id,
                )
                await query.edit_message_text("Unauthorized: this recommendation is not yours.")
                return

            if action == "approve":
                from adcopilot.application.use_cases.approve_recommendation import (
                    ApproveRecommendationUseCase,
                )

                await ApproveRecommendationUseCase(rec_repo).execute(rec_id)

            elif action == "decline":
                from adcopilot.application.use_cases.decline_recommendation import (
                    DeclineRecommendationUseCase,
                )

                await DeclineRecommendationUseCase(rec_repo).execute(rec_id)

            elif action == "snooze":
                from adcopilot.application.use_cases.snooze_recommendation import (
                    SnoozeRecommendationUseCase,
                )

                snooze_repo = SqlSnoozeRepository(session)
                await SnoozeRecommendationUseCase(rec_repo, snooze_repo).execute(rec_id)

    except Exception:
        logger.exception("callback handler error", action=action, rec_id=rec_id_str)
        await query.edit_message_text("An error occurred. Please try again.")
        return
    finally:
        await engine.dispose()

    label = _ACTION_LABELS[action]
    logger.info("recommendation action taken", action=action, rec_id=rec_id_str)
    await query.edit_message_text(f"✓ {label}")


async def undo_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle undo_exec:{rec_id} inline button presses."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    parts = query.data.split(":", 1)
    if len(parts) != 2:
        return

    _, rec_id_str = parts
    telegram_chat_id = query.from_user.id if query.from_user else None
    if telegram_chat_id is None:
        return

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            from sqlalchemy import select

            from adcopilot.domain.entities import UserId
            from adcopilot.domain.recommendation import RecommendationId
            from adcopilot.infrastructure.db.models import UserModel
            from adcopilot.infrastructure.db.repositories.audit_log_repository import (
                SqlAuditLogRepository,
            )
            from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
                SqlGoogleAdsAccountRepository,
            )
            from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
                SqlOAuthCredentialsRepository,
            )
            from adcopilot.infrastructure.db.repositories.recommendation_repository import (
                SqlRecommendationRepository,
            )
            from adcopilot.infrastructure.google_ads.mutations_adapter import (
                GoogleAdsMutationsAdapter,
            )

            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id == telegram_chat_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                await query.edit_message_text("Unauthorized: Telegram account not linked.")
                return

            user_id = UserId(str(user_model.id))
            rec_repo = SqlRecommendationRepository(session)
            account_repo = SqlGoogleAdsAccountRepository(session)
            rec_id = RecommendationId(rec_id_str)
            rec = await rec_repo.get(rec_id)
            if rec is None:
                await query.edit_message_text("Recommendation not found.")
                return

            # Security: verify ownership
            user_accounts = await account_repo.list_for_user(user_id)
            if rec.account_id not in {a.id for a in user_accounts}:
                await query.edit_message_text("Unauthorized: this recommendation is not yours.")
                return

            from adcopilot.application.use_cases.undo_recommendation import (
                UndoRecommendationUseCase,
            )

            use_case = UndoRecommendationUseCase(
                rec_repo=rec_repo,
                audit_log_repo=SqlAuditLogRepository(session),
                account_repo=account_repo,
                credentials_repo=SqlOAuthCredentialsRepository(
                    session, settings.TOKEN_ENCRYPTION_KEY
                ),
                mutations=GoogleAdsMutationsAdapter(settings),
            )
            await use_case.execute(rec_id)

    except ValueError as exc:
        await query.edit_message_text(f"Cannot undo: {exc}")
        return
    except Exception:
        logger.exception("undo callback error", rec_id=rec_id_str)
        await query.edit_message_text("An error occurred while undoing. Please try again.")
        return
    finally:
        await engine.dispose()

    logger.info("recommendation undone via telegram", rec_id=rec_id_str)
    await query.edit_message_text("✓ Action undone successfully.")
