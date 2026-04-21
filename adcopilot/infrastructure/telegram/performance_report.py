"""Telegram performance report formatter — weekly impact summary for approved recommendations."""

from __future__ import annotations

import structlog
from telegram import Bot

from adcopilot.application.detection.templates import format_micros_as_currency
from adcopilot.domain.performance_tracking import PerformanceComparison

logger = structlog.get_logger(__name__)

_VERDICT_EMOJI = {
    "IMPROVED": "✅",
    "NEUTRAL": "⚠️",
    "DEGRADED": "❌",
}


def _format_comparison_line(comp: PerformanceComparison, kind_label: str) -> str:
    emoji = _VERDICT_EMOJI.get(comp.verdict, "➖")
    if comp.verdict == "IMPROVED":
        savings_micros = int(abs(comp.delta_cpa_pct / 100) * comp.current_cpa_micros * comp.current_conversions * 4)
        savings_str = format_micros_as_currency(savings_micros)
        delta_str = f"CPA -{abs(comp.delta_cpa_pct):.0f}% (oszczędności ~{savings_str})"
    elif comp.verdict == "DEGRADED":
        delta_str = f"CPA +{comp.delta_cpa_pct:.0f}% — pogorszenie"
    else:
        delta_str = "brak znaczącej zmiany"
    return f"{emoji} {kind_label} → {delta_str}"


def format_weekly_report(
    account_name: str,
    comparisons: list[tuple[PerformanceComparison, str]],
    cumulative_savings_micros: int = 0,
) -> str:
    if not comparisons:
        return ""

    improved = [(c, k) for c, k in comparisons if c.verdict == "IMPROVED"]
    neutral = [(c, k) for c, k in comparisons if c.verdict == "NEUTRAL"]
    degraded = [(c, k) for c, k in comparisons if c.verdict == "DEGRADED"]

    lines = [f"📈 *Podsumowanie tygodnia — {account_name}*", ""]
    lines.append("Za ostatnie 7 dni Twoje zatwierdzone rekomendacje:")

    for comp, kind_label in improved + neutral + degraded:
        lines.append(_format_comparison_line(comp, kind_label))

    if cumulative_savings_micros > 0:
        lines.append("")
        lines.append(f"Łączne oszczędności od początku: {format_micros_as_currency(cumulative_savings_micros)}")

    return "\n".join(lines)


class TelegramPerformanceReporter:
    def __init__(self, bot_token: str) -> None:
        self._bot = Bot(token=bot_token)

    async def send_report(
        self,
        chat_id: int,
        account_name: str,
        comparisons: list[tuple[PerformanceComparison, str]],
        cumulative_savings_micros: int = 0,
    ) -> None:
        text = format_weekly_report(account_name, comparisons, cumulative_savings_micros)
        if not text:
            logger.info("no comparisons to report, skipping", chat_id=chat_id)
            return
        await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        logger.info("performance report sent", chat_id=chat_id, comparisons=len(comparisons))
