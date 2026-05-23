"""SQLAlchemy implementation of PerformanceComparisonRepository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.performance_tracking import PerformanceComparison
from adcopilot.domain.recommendation import RecommendationId
from adcopilot.infrastructure.db.models import PerformanceComparisonModel


def _model_to_domain(m: PerformanceComparisonModel) -> PerformanceComparison:
    return PerformanceComparison(
        id=str(m.id),
        recommendation_id=RecommendationId(str(m.recommendation_id)),
        baseline_id=str(m.baseline_id),
        comparison_window_days=m.comparison_window_days,
        current_cost_micros=m.current_cost_micros,
        current_clicks=m.current_clicks,
        current_impressions=m.current_impressions,
        current_conversions=m.current_conversions,
        current_cpa_micros=m.current_cpa_micros,
        delta_cpa_pct=m.delta_cpa_pct,
        delta_conversions_pct=m.delta_conversions_pct,
        delta_ctr_pct=m.delta_ctr_pct,
        verdict=m.verdict,  # type: ignore[arg-type]
        compared_at=m.compared_at,
    )


class SqlPerformanceComparisonRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, comparison: PerformanceComparison) -> None:
        m = PerformanceComparisonModel()
        m.id = uuid.UUID(comparison.id)
        m.recommendation_id = uuid.UUID(comparison.recommendation_id)
        m.baseline_id = uuid.UUID(comparison.baseline_id)
        m.comparison_window_days = comparison.comparison_window_days
        m.current_cost_micros = comparison.current_cost_micros
        m.current_clicks = comparison.current_clicks
        m.current_impressions = comparison.current_impressions
        m.current_conversions = comparison.current_conversions
        m.current_cpa_micros = comparison.current_cpa_micros
        m.delta_cpa_pct = comparison.delta_cpa_pct
        m.delta_conversions_pct = comparison.delta_conversions_pct
        m.delta_ctr_pct = comparison.delta_ctr_pct
        m.verdict = comparison.verdict
        m.compared_at = comparison.compared_at
        self._session.add(m)
        await self._session.flush()

    async def exists(self, recommendation_id: RecommendationId, window_days: int) -> bool:
        result = await self._session.execute(
            select(PerformanceComparisonModel).where(
                PerformanceComparisonModel.recommendation_id == uuid.UUID(recommendation_id),
                PerformanceComparisonModel.comparison_window_days == window_days,
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_for_account(
        self, account_id: str, limit: int = 50
    ) -> list[PerformanceComparison]:
        from adcopilot.infrastructure.db.models import RecommendationModel

        result = await self._session.execute(
            select(PerformanceComparisonModel)
            .join(
                RecommendationModel,
                PerformanceComparisonModel.recommendation_id == RecommendationModel.id,
            )
            .where(RecommendationModel.account_id == uuid.UUID(account_id))
            .order_by(PerformanceComparisonModel.compared_at.desc())
            .limit(limit)
        )
        return [_model_to_domain(m) for m in result.scalars().all()]
