"""Run the Telegram bot in polling mode (local development only).

Usage:
    python scripts/run_bot.py

This script is intentionally blocked in production.  Set
``TELEGRAM_WEBHOOK_URL`` in your environment and let the FastAPI app register
the webhook automatically on startup instead.
"""

from __future__ import annotations

import sys

from telegram import Update

from adcopilot.config import get_settings
from adcopilot.infrastructure.telegram.bot import build_telegram_app


def main() -> None:
    settings = get_settings()

    if settings.is_production:
        print(
            "ERROR: polling mode is disabled in production.\n"
            "Set TELEGRAM_WEBHOOK_URL so the FastAPI app registers the webhook "
            "automatically on startup.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Delete any registered webhook so Telegram delivers updates via polling
    # rather than HTTP push.  This prevents silent message loss when switching
    # from a previously deployed webhook URL back to local development.
    import asyncio

    from telegram import Bot

    async def _clear_webhook() -> None:
        async with Bot(token=settings.TELEGRAM_BOT_TOKEN or "") as bot:
            await bot.delete_webhook(drop_pending_updates=False)

    asyncio.run(_clear_webhook())

    app = build_telegram_app(settings)
    print("Starting bot in polling mode… (Ctrl-C to stop)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
