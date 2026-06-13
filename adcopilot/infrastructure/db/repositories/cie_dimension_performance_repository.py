"""SQL implementation of CieDimensionPerformanceRepository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    DimensionPerformance,
)
from adcopilot.infrastructure.db.models import DimensionPerformanceModel


def _to_domain(m: DimensionPerformanceModel) -> DimensionPerformance:
    return DimensionPerformance(
        vertical=m.vertical,
        dimension=m.dimension,
        value=m.value,
        sample_size=m.sample_size,
        clicks=m.clicks,
        conversions=m.conversions,
        weighted_ctr=m.weighted_ctr,
        weighted_conv=m.weighted_conv,
        smoothed_score=m.smoothed_score,
        language=m.language,
    )


class SqlCieDimensionPerformanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, p: DimensionPerformance) -> None:
        stmt = pg_insert(DimensionPerformanceModel).values(
            vertical=p.vertical,
            dimension=p.dimension,
            value=p.value,
            language=p.language,
            sample_size=p.sample_size,
            clicks=p.clicks,
            conversions=p.conversions,
            weighted_ctr=p.weighted_ctr,
            weighted_conv=p.weighted_conv,
            smoothed_score=p.smoothed_score,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_cie_dimension_performance_key",
            set_={
                "sample_size": stmt.excluded.sample_size,
                "clicks": stmt.excluded.clicks,
                "conversions": stmt.excluded.conversions,
                "weighted_ctr": stmt.excluded.weighted_ctr,
                "weighted_conv": stmt.excluded.weighted_conv,
                "smoothed_score": stmt.excluded.smoothed_score,
            },
        )
        await self._session.execute(stmt)

    async def get_map(
        self, *, vertical: str, dimension: str, language: str = "pl"
    ) -> dict[str, DimensionPerformance]:
        result = await self._session.execute(
            select(DimensionPerformanceModel).where(
                DimensionPerformanceModel.vertical == vertical,
                DimensionPerformanceModel.dimension == dimension,
                DimensionPerformanceModel.language == language,
            )
        )
        return {m.value: _to_domain(m) for m in result.scalars().all()}
