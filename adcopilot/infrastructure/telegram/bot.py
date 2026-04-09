"""Telegram bot setup — polling mode for local dev, webhook for prod."""

from __future__ import annotations

import structlog
from telegram.ext import Application, CommandHandler

from adcopilot.config import Settings

logger = structlog.get_logger(__name__)


def build_telegram_app(settings: Settings) -> Application:  # type: ignore[type-arg]
    """Build and configure the python-telegram-bot Application."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    from adcopilot.infrastructure.telegram.handlers import start_handler

    app: Application = (  # type: ignore[type-arg]
        Application.builder().token(token).build()
    )
    app.add_handler(CommandHandler("start", start_handler))
    return app
