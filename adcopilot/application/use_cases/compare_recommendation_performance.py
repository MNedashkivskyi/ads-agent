"""CompareRecommendationPerformanceUseCase: daily task comparing executed recs against baselines."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from adcopilot.application.ports.performance_baseline_repository import (
    PerformanceBaselineRepository,
)
from adcopilot.application.ports.performance_comparison_repository import (
    PerformanceComparisonRepository,
)
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.domain.performance_tracking import PerformanceComparison
from adcopilot.domain.recommendation import RecommendationId

logger = structlog.get_logger(__name__)

_WINDOWS = (7, 14)
_TOLERANCE_DAYS = 1


class CompareRecommendationPerformanceUseCase:
    def __init__(
        self,
        rec_repo: RecommendationRepository,
        baseline_repo: PerformanceBaselineRepository,
        comparison_repo: PerformanceComparisonRepository,
        snapshot_fetcher: Any,  # callable(account_id, entity_type, entity_id) -> metrics dict
    ) -> None:
        self._rec_repo = rec_repo
        self._baseline_repo = baseline_repo
        self._comparison_repo = comparison_repo
        self._snapshot_fetcher = snapshot_fetcher

    async def run(self, now: datetime | None = None) -> dict[str, int]:
        if now is None:
            now = datetime.now(UTC)

        comparisons_created = 0
        comparisons_skipped = 0
        errors = 0

        for window_days in _WINDOWS:
            target_date = (now - timedelta(days=window_days)).date()
            window_start = target_date - timedelta(days=_TOLERANCE_DAYS)
            window_end = target_date + timedelta(days=_TOLERANCE_DAYS)

            recs = await self._rec_repo.list_executed_in_date_range(window_start, window_end)
            for rec in recs:
                try:
                    already_exists = await self._comparison_repo.exists(
                        RecommendationId(rec.id), window_days
                    )
                    if already_exists:
                        comparisons_skipped += 1
                        continue

                    baseline = await self._baseline_repo.get_by_recommendation(RecommendationId(rec.id))
                    if baseline is None:
                        comparisons_skipped += 1
                        continue

                    current = await self._snapshot_fetcher(
                        account_id=rec.account_id,
                        entity_type=baseline.entity_type,
                        entity_id=baseline.entity_id,
                    )
                    if current is None:
                        comparisons_skipped += 1
                        continue

                    comparison = PerformanceComparison.create(
                        recommendation_id=RecommendationId(rec.id),
                        baseline=baseline,
                        comparison_window_days=window_days,
                        current_cost_micros=current.get("cost_micros", 0),
                        current_clicks=current.get("clicks", 0),
                        current_impressions=current.get("impressions", 0),
                        current_conversions=current.get("conversions", 0.0),
                        compared_at=now,
                    )
                    await self._comparison_repo.save(comparison)
                    comparisons_created += 1
                    logger.info(
                        "performance comparison created",
                        rec_id=rec.id,
                        window_days=window_days,
                        verdict=comparison.verdict,
                    )
                except Exception:
                    logger.exception("comparison failed", rec_id=rec.id, window_days=window_days)
                    errors += 1

        return {
            "comparisons_created": comparisons_created,
            "comparisons_skipped": comparisons_skipped,
            "errors": errors,
        }
