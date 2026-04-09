"""Telegram command handlers."""

from __future__ import annotations

import dataclasses

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from telegram import Update
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
