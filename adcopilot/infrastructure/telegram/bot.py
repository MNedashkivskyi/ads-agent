"""Telegram bot setup — polling mode for local dev, webhook for prod."""

from __future__ import annotations

import hashlib
import hmac

import structlog
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from adcopilot.config import Settings

logger = structlog.get_logger(__name__)


def compute_webhook_secret(bot_token: str) -> str:
    """Derive a deterministic webhook secret from the bot token.

    The same value is passed to ``setWebhook`` as ``secret_token`` and checked
    against the ``X-Telegram-Bot-Api-Secret-Token`` header on every incoming
    update.  Using the bot token as the key means we never need to store an
    extra secret.
    """
    return hmac.new(b"WebhookSecret", bot_token.encode(), hashlib.sha256).hexdigest()


async def register_webhook(bot: object, webhook_url: str, secret: str) -> None:
    """Register ``webhook_url`` with the Telegram Bot API.

    Idempotent — safe to call on every startup.
    """
    from telegram import Bot  # local import to avoid heavy top-level cost

    assert isinstance(bot, Bot)
    await bot.set_webhook(url=webhook_url, secret_token=secret)
    logger.info("telegram webhook registered", url=webhook_url)


def build_telegram_app(settings: Settings) -> Application:  # type: ignore[type-arg]
    """Build and configure the python-telegram-bot Application."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    from adcopilot.infrastructure.telegram.callback_handler import (
        more_callback_handler,
        recommendation_callback_handler,
        undo_callback_handler,
    )
    from adcopilot.infrastructure.telegram.handlers import (
        fallback_handler,
        help_handler,
        history_handler,
        pause_handler,
        resume_handler,
        start_handler,
        status_handler,
        undo_handler,
    )

    app: Application = (  # type: ignore[type-arg]
        Application.builder().token(token).build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(CommandHandler("history", history_handler))
    app.add_handler(CommandHandler("pause", pause_handler))
    app.add_handler(CommandHandler("resume", resume_handler))
    app.add_handler(CommandHandler("undo", undo_handler))
    app.add_handler(CommandHandler("help", help_handler))

    # Callback query handlers (order matters — more specific patterns first)
    app.add_handler(CallbackQueryHandler(undo_callback_handler, pattern=r"^undo_exec:"))
    app.add_handler(CallbackQueryHandler(more_callback_handler, pattern=r"^more:"))
    app.add_handler(
        CallbackQueryHandler(
            recommendation_callback_handler,
            pattern=r"^(approve|decline|snooze):",
        )
    )

    # Fallback: catch any non-command text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_handler))

    return app
