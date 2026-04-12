"""Telegram digest notifier — sends recommendation cards with inline action buttons."""

from __future__ import annotations

import structlog
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from adcopilot.application.detection.templates import format_micros_as_currency
from adcopilot.domain.recommendation import NON_EXECUTABLE_KINDS, Recommendation, RecommendationSeverity

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


def _action_keyboard(rec: Recommendation) -> InlineKeyboardMarkup:
    rec_id = rec.id
    if rec.kind in NON_EXECUTABLE_KINDS:
        # Advisory card — no Approve button to avoid runtime errors from missing executors
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("❌ Odrzuć", callback_data=f"decline:{rec_id}"),
                    InlineKeyboardButton("💬 Szczegóły", callback_data=f"more:{rec_id}"),
                    InlineKeyboardButton("⏰ Odłóż", callback_data=f"snooze:{rec_id}"),
                ]
            ]
        )
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
            keyboard = _action_keyboard(rec)
            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
        logger.info("digest sent via telegram", chat_id=chat_id, count=len(recommendations))

    async def send_execution_failed(
        self, chat_id: int, recommendation: Recommendation, error_message: str
    ) -> None:
        """Notify the user that an approved recommendation could not be executed."""
        kind_label = recommendation.kind.value.replace("_", " ").title()
        text = (
            f"\u274c *Nie udało się wykonać rekomendacji*\n\n"
            f"*Rodzaj:* {kind_label}\n"
            f"*Błąd:* {error_message}\n\n"
            "Spróbuj ponownie lub skontaktuj się z pomocą techniczną."
        )
        await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        logger.warning(
            "execution failed notification sent",
            chat_id=chat_id,
            rec_id=recommendation.id,
            kind=recommendation.kind.value,
        )

    async def send_reauth_required(
        self, chat_id: int, account_name: str, reauth_url: str | None = None
    ) -> None:
        """Notify the user that their Google Ads token is invalid and they must re-authorize."""
        if reauth_url:
            cta = f"Kliknij tutaj, aby ponownie połączyć konto: {reauth_url}"
        else:
            cta = "Zaloguj się ponownie w aplikacji, aby wznowić zarządzanie reklamami."
        text = (
            "\U0001f512 *Utracono dostęp do konta Google Ads*\n\n"
            f"Token OAuth dla konta *{account_name}* wygasł lub został odwołany.\n\n"
            f"{cta}"
        )
        await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        logger.warning(
            "reauth required notification sent",
            chat_id=chat_id,
            account_name=account_name,
        )
