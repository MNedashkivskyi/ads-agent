"""SendPerformanceReportUseCase: send weekly Telegram report on approved recommendation impact."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from adcopilot.application.ports.performance_comparison_repository import (
    PerformanceComparisonRepository,
)
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.application.ports.repositories import GoogleAdsAccountRepository

logger = structlog.get_logger(__name__)

_REPORT_WINDOW_DAYS = 14


class SendPerformanceReportUseCase:
    def __init__(
        self,
        account_repo: GoogleAdsAccountRepository,
        rec_repo: RecommendationRepository,
        comparison_repo: PerformanceComparisonRepository,
        reporter: Any,  # TelegramPerformanceReporter
    ) -> None:
        self._account_repo = account_repo
        self._rec_repo = rec_repo
        self._comparison_repo = comparison_repo
        self._reporter = reporter

    async def run(self, now: datetime | None = None) -> dict[str, int]:
        if now is None:
            now = datetime.now(UTC)

        accounts = await self._account_repo.list_active()
        reports_sent = 0
        reports_skipped = 0

        for account in accounts:
            try:
                comparisons_raw = await self._comparison_repo.list_for_account(
                    str(account.id), limit=50
                )

                # Filter to last 14 days
                cutoff = now - timedelta(days=_REPORT_WINDOW_DAYS)
                recent = [
                    c for c in comparisons_raw
                    if c.compared_at.replace(tzinfo=UTC) >= cutoff
                    if c.compared_at.tzinfo is None or c.compared_at >= cutoff
                ]
                if not recent:
                    reports_skipped += 1
                    continue

                # Pair comparisons with rec kind labels
                pairs = []
                for comp in recent:
                    rec = await self._rec_repo.get(comp.recommendation_id)
                    kind_label = rec.kind.value.replace("_", " ").title() if rec else "Rekomendacja"
                    pairs.append((comp, kind_label))

                # Compute cumulative savings from IMPROVED comparisons
                cumulative = sum(
                    int(abs(c.delta_cpa_pct / 100) * c.current_cpa_micros * c.current_conversions * 4)
                    for c, _ in pairs
                    if c.verdict == "IMPROVED"
                )

                account_name = getattr(account, "name", str(account.id))
                await self._reporter.send_report(
                    chat_id=int(account.telegram_chat_id),
                    account_name=account_name,
                    comparisons=pairs,
                    cumulative_savings_micros=cumulative,
                )
                reports_sent += 1
                logger.info("weekly performance report sent", account_id=str(account.id))
            except Exception:
                logger.exception("performance report failed", account_id=str(account.id))
                reports_skipped += 1

        return {"reports_sent": reports_sent, "reports_skipped": reports_skipped}
