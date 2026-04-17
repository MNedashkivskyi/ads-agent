"""Sends immediate URGENT alert messages to Telegram."""
from __future__ import annotations

import structlog
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from adcopilot.application.detection.templates import format_micros_as_currency
from adcopilot.domain.alert import Alert, AlertKind

logger = structlog.get_logger(__name__)


def _format_impact(alert: Alert) -> str:
    """Extract a human-readable impact figure from alert payload."""
    payload = alert.payload
    # Try common payload keys
    micros = (
        payload.get("current_spend_micros")
        or payload.get("total_budget_micros")
        or 0
    )
    if micros:
        return format_micros_as_currency(int(micros))
    return "—"


def _format_alert_message(alert: Alert, account_name: str) -> str:
    impact = _format_impact(alert)
    return (
        f"⚠️ *URGENT — {account_name}*\n"
        f"{alert.message}\n"
        f"Current impact: {impact}"
    )


def _alert_keyboard(alert: Alert) -> InlineKeyboardMarkup:
    alert_id = alert.id
    account_id = str(alert.account_id)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🛑 Pause campaign", callback_data=f"alert_pause:{alert_id}"),
                InlineKeyboardButton("👀 Investigate", callback_data=f"alert_investigate:{account_id}"),
                InlineKeyboardButton("✓ This is expected", callback_data=f"alert_ack:{alert_id}"),
            ]
        ]
    )


class AlertNotifier:
    """Sends immediate critical alert messages to a Telegram chat."""

    def __init__(self, bot_token: str) -> None:
        self._bot = Bot(token=bot_token)

    async def send_alert(
        self,
        chat_id: int,
        alert: Alert,
        account_name: str,
    ) -> None:
        """Send an immediate URGENT alert card to *chat_id*."""
        text = _format_alert_message(alert, account_name)
        keyboard = _alert_keyboard(alert)
        await self._bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        logger.info(
            "alert sent via telegram",
            chat_id=chat_id,
            alert_id=alert.id,
            kind=alert.kind.value,
        )
