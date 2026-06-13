"""recompute_dimension_weights — ONE learner, both tracks.

Aggregates the accumulated performance facts into ``dimension_performance`` per
(vertical, dimension, value, language), Bayesian-smoothed toward the
(vertical, language) prior. The same code path computes "PROBLEM keywords convert
best in beauty" and "failed-alternative hooks convert best in beauty" — only the
``dimension`` differs.
"""

from __future__ import annotations

from collections import defaultdict

import structlog

from adcopilot.application.ports.cie_dimension_performance_repository import (
    CieDimensionPerformanceRepository,
)
from adcopilot.application.ports.cie_performance import (
    CiePerformanceFactRepository,
    DimensionAggregate,
)
from adcopilot.domain.campaign_intelligence.creatives.angle import ANGLE_DIMENSION
from adcopilot.domain.campaign_intelligence.keywords.value_objects import (
    KEYWORD_INTENT_DIMENSION,
)
from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    DimensionPerformance,
)

logger = structlog.get_logger(__name__)

DEFAULT_DIMENSIONS = (KEYWORD_INTENT_DIMENSION, ANGLE_DIMENSION)


class RecomputeDimensionWeightsUseCase:
    def __init__(
        self,
        fact_repo: CiePerformanceFactRepository,
        dim_perf_repo: CieDimensionPerformanceRepository,
    ) -> None:
        self._facts = fact_repo
        self._dim_perf = dim_perf_repo

    async def run(self, dimensions: tuple[str, ...] = DEFAULT_DIMENSIONS) -> dict[str, int]:
        written: dict[str, int] = {}
        for dimension in dimensions:
            aggregates = await self._facts.aggregate_by_dimension(dimension)
            written[dimension] = await self._recompute_dimension(dimension, aggregates)
        logger.info("cie.recompute_weights", **written)
        return written

    async def _recompute_dimension(
        self, dimension: str, aggregates: list[DimensionAggregate]
    ) -> int:
        # Group by (vertical, language) so the prior is computed across the
        # values that actually compete with each other.
        groups: dict[tuple[str, str], list[DimensionAggregate]] = defaultdict(list)
        for agg in aggregates:
            groups[(agg.vertical, agg.language)].append(agg)

        count = 0
        for (vertical, language), members in groups.items():
            total_impr = sum(m.impressions for m in members)
            total_clicks = sum(m.clicks for m in members)
            total_conv = sum(m.conversions for m in members)
            prior_ctr = (total_clicks / total_impr) if total_impr > 0 else 0.0
            prior_conv = (total_conv / total_clicks) if total_clicks > 0 else 0.0

            for m in members:
                perf = DimensionPerformance.from_aggregates(
                    vertical=vertical,
                    dimension=dimension,
                    value=m.value,
                    impressions=m.impressions,
                    clicks=m.clicks,
                    conversions=m.conversions,
                    prior_ctr=prior_ctr,
                    prior_conv=prior_conv,
                    language=language,
                )
                await self._dim_perf.upsert(perf)
                count += 1
        return count
