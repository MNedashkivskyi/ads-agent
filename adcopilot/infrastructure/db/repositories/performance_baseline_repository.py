"""SQLAlchemy implementation of PerformanceBaselineRepository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import AccountId
from adcopilot.domain.performance_tracking import PerformanceBaseline
from adcopilot.domain.recommendation import RecommendationId
from adcopilot.infrastructure.db.models import PerformanceBaselineModel


def _model_to_domain(m: PerformanceBaselineModel) -> PerformanceBaseline:
    return PerformanceBaseline(
        id=str(m.id),
        recommendation_id=RecommendationId(str(m.recommendation_id)),
        account_id=AccountId(str(m.account_id)),
        entity_type=m.entity_type,  # type: ignore[arg-type]
        entity_id=m.entity_id,
        baseline_date=m.baseline_date,
        cost_micros=m.cost_micros,
        clicks=m.clicks,
        impressions=m.impressions,
        conversions=m.conversions,
        conv_value=m.conv_value,
        cpa_micros=m.cpa_micros,
        ctr=m.ctr,
        captured_at=m.captured_at,
    )


class SqlPerformanceBaselineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, baseline: PerformanceBaseline) -> None:
        m = PerformanceBaselineModel()
        m.id = uuid.UUID(baseline.id)
        m.recommendation_id = uuid.UUID(baseline.recommendation_id)
        m.account_id = uuid.UUID(baseline.account_id)
        m.entity_type = baseline.entity_type
        m.entity_id = baseline.entity_id
        m.baseline_date = baseline.baseline_date
        m.cost_micros = baseline.cost_micros
        m.clicks = baseline.clicks
        m.impressions = baseline.impressions
        m.conversions = baseline.conversions
        m.conv_value = baseline.conv_value
        m.cpa_micros = baseline.cpa_micros
        m.ctr = baseline.ctr
        m.captured_at = baseline.captured_at
        self._session.add(m)
        await self._session.flush()

    async def get_by_recommendation(
        self, recommendation_id: RecommendationId
    ) -> PerformanceBaseline | None:
        result = await self._session.execute(
            select(PerformanceBaselineModel).where(
                PerformanceBaselineModel.recommendation_id == uuid.UUID(recommendation_id)
            )
        )
        m = result.scalar_one_or_none()
        return _model_to_domain(m) if m else None
