"""Telegram command handlers."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from adcopilot.config import get_settings
from adcopilot.domain.entities import UserId
from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository
from adcopilot.interfaces.api.telegram import _verify_link_jwt

logger = structlog.get_logger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command.

    If a deep-link parameter (JWT) is present, decode it, find the user,
    set telegram_chat_id, and confirm. Otherwise show sign-up instructions.
    """
    if update.message is None:
        return

    chat_id = update.message.chat_id
    args: list[str] = list(context.args or [])

    if not args:
        await update.message.reply_text(
            "Welcome to AdCopilot! Please sign up at the web app and link your Telegram account."
        )
        return

    deep_link_token = args[0]
    settings = get_settings()

    user_id = _verify_link_jwt(deep_link_token, settings.SECRET_KEY)
    if user_id is None:
        await update.message.reply_text("Invalid or expired link. Please request a new one.")
        return

    # Fetch and update the user
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            repo = SqlUserRepository(session)
            user = await repo.get_by_id(UserId(user_id))
            if user is None:
                await update.message.reply_text("User not found. Please sign up first.")
                return

            updated = dataclasses.replace(user, telegram_chat_id=chat_id)
            await repo.save(updated)
            await session.commit()
    finally:
        await engine.dispose()

    await update.message.reply_text(
        f"Your Telegram account has been linked successfully! Welcome, {user.email}."
    )
    logger.info("telegram linked", user_id=user_id, chat_id=chat_id)


async def undo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/undo — lists the last executed recommendations with Undo buttons (7-day window)."""
    if update.message is None:
        return

    chat_id = update.message.chat_id
    settings = get_settings()

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from sqlalchemy import select

            from adcopilot.domain.entities import AccountId
            from adcopilot.infrastructure.db.models import UserModel
            from adcopilot.infrastructure.db.repositories.audit_log_repository import (
                SqlAuditLogRepository,
            )
            from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
                SqlGoogleAdsAccountRepository,
            )

            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id == chat_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                await update.message.reply_text(
                    "Your Telegram account is not linked. Use /start with your link token."
                )
                return

            account_repo = SqlGoogleAdsAccountRepository(session)
            audit_repo = SqlAuditLogRepository(session)

            accounts = await account_repo.list_for_user(UserId(str(user_model.id)))
            account_ids = [AccountId(a.id) for a in accounts]

            since = datetime.now(UTC) - timedelta(days=7)
            recent = await audit_repo.list_recent_executes(account_ids, since)

            if not recent:
                await update.message.reply_text(
                    "No executed recommendations in the last 7 days. Nothing to undo."
                )
                return

            # Deduplicate by recommendation_id, keep newest
            seen: set[str] = set()
            unique = []
            for log in recent:
                if log.recommendation_id not in seen:
                    seen.add(log.recommendation_id)
                    unique.append(log)
                    if len(unique) == 5:
                        break

            await update.message.reply_text(
                f"Your last {len(unique)} executed action(s) — tap Undo to reverse:"
            )
            for log in unique:
                kind_label = log.kind.replace("_", " ").title()
                ts = log.created_at.strftime("%Y-%m-%d %H:%M UTC")
                text = f"{kind_label} — executed {ts}"
                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Undo", callback_data=f"undo_exec:{log.recommendation_id}")]]
                )
                await update.message.reply_text(text, reply_markup=keyboard)
    finally:
        await engine.dispose()
