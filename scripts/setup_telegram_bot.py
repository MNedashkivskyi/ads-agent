"""One-time Telegram bot configuration script.

Run once after deploy to register commands and descriptions:
    python scripts/setup_telegram_bot.py
"""

from __future__ import annotations

import asyncio
import sys

from telegram import Bot, BotCommand

from adcopilot.config import get_settings

COMMANDS = [
    BotCommand("connect", "Connect Google Ads account"),
    BotCommand("status", "Account summary"),
    BotCommand("history", "Recent recommendations"),
    BotCommand("pause", "Pause daily recommendations"),
    BotCommand("resume", "Resume recommendations"),
    BotCommand("undo", "Reverse a recent change"),
    BotCommand("help", "Available commands"),
]

DESCRIPTION = (
    "Adept — Professional Google Ads optimization. "
    "Connect your account at tryadept.com to get started."
)

SHORT_DESCRIPTION = (
    "Adept monitors your Google Ads account and sends optimization "
    "recommendations you can approve or decline right here."
)


async def main() -> None:
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set in .env", file=sys.stderr)
        sys.exit(1)

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

    async with bot:
        await bot.set_my_commands(COMMANDS)
        print(f"✓ Registered {len(COMMANDS)} commands")

        await bot.set_my_description(DESCRIPTION)
        print("✓ Set bot description")

        await bot.set_my_short_description(SHORT_DESCRIPTION)
        print("✓ Set bot short description")

        info = await bot.get_me()
        print(f"✓ Bot configured: @{info.username} ({info.full_name})")


if __name__ == "__main__":
    asyncio.run(main())
