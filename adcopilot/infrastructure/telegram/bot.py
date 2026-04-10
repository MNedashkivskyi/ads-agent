"""Telegram bot setup — polling mode for local dev, webhook for prod."""

from __future__ import annotations

import structlog
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from adcopilot.config import Settings

logger = structlog.get_logger(__name__)


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
