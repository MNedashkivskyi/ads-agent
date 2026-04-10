"""Telegram digest notifier — sends recommendation cards with inline action buttons."""

from __future__ import annotations

import structlog
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from adcopilot.application.detection.templates import format_micros_as_currency
from adcopilot.domain.recommendation import Recommendation, RecommendationSeverity

logger = structlog.get_logger(__name__)

_SEVERITY_EMOJI = {
    RecommendationSeverity.CRITICAL: "\U0001f534",  # red circle
    RecommendationSeverity.HIGH: "\U0001f7e0",      # orange circle
    RecommendationSeverity.MEDIUM: "\U0001f7e1",    # yellow circle
    RecommendationSeverity.LOW: "\U0001f7e2",       # green circle
}


def _format_card(rec: Recommendation) -> str:
    emoji = _SEVERITY_EMOJI.get(rec.severity, "")
    savings = format_micros_as_currency(rec.estimated_monthly_savings_micros)
    kind_label = rec.kind.value.replace("_", " ").title()
    header = f"{emoji} *{kind_label}* — oszczędności {savings}/mies."
    body = rec.explanation or kind_label
    return f"{header}\n{body}"


def _action_keyboard(rec_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Zatwierdź", callback_data=f"approve:{rec_id}"),
                InlineKeyboardButton("❌ Odrzuć", callback_data=f"decline:{rec_id}"),
                InlineKeyboardButton("💬 Szczegóły", callback_data=f"more:{rec_id}"),
                InlineKeyboardButton("⏰ Odłóż", callback_data=f"snooze:{rec_id}"),
            ]
        ]
    )


def _digest_header(account_name: str, count: int, total_savings_micros: int) -> str:
    savings = format_micros_as_currency(total_savings_micros)
    n_word = "rekomendację" if count == 1 else "rekomendacji"
    return (
        f"📊 *Dzisiejszy raport — {account_name}*\n"
        f"Znalazłem {count} {n_word} dla Twojego konta.\n"
        f"Potencjalne oszczędności: ~{savings}/mies."
    )


class TelegramDigestNotifier:
    """Sends recommendation digest cards to a Telegram chat."""

    def __init__(self, bot_token: str) -> None:
        self._bot = Bot(token=bot_token)

    async def send_digest(self, chat_id: int, recommendations: list[Recommendation]) -> None:
        total_savings = sum(r.estimated_monthly_savings_micros for r in recommendations)
        header = _digest_header(
            account_name="Twoje konto",
            count=len(recommendations),
            total_savings_micros=total_savings,
        )
        await self._bot.send_message(
            chat_id=chat_id,
            text=header,
            parse_mode="Markdown",
        )
        for rec in recommendations:
            text = _format_card(rec)
            keyboard = _action_keyboard(rec.id)
            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
        logger.info("digest sent via telegram", chat_id=chat_id, count=len(recommendations))
