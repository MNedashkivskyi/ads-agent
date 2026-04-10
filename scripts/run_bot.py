"""Run the Telegram bot in polling mode (local development).

    python scripts/run_bot.py
"""

from __future__ import annotations

from telegram import Update

from adcopilot.config import get_settings
from adcopilot.infrastructure.telegram.bot import build_telegram_app


def main() -> None:
    settings = get_settings()
    app = build_telegram_app(settings)
    print("Starting bot in polling mode…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
