"""rank_keywords — load a run's validated candidates and build the comparison."""

from __future__ import annotations

from adcopilot.application.ports.cie_keyword_repository import CieKeywordRepository
from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import KeywordStatus
from adcopilot.domain.campaign_intelligence.keywords.keyword_comparison import (
    KeywordComparison,
    build_comparison,
)
from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    DimensionPerformance,
)


class RankKeywordsUseCase:
    def __init__(self, repo: CieKeywordRepository) -> None:
        self._repo = repo

    async def run(
        self,
        run_id: str,
        *,
        learned_weights: dict[str, float] | None = None,
        performance: dict[str, DimensionPerformance] | None = None,
    ) -> KeywordComparison:
        candidates = await self._repo.list_candidates(
            run_id, statuses=[KeywordStatus.VALIDATED.value]
        )
        return build_comparison(
            candidates, learned_weights=learned_weights, performance=performance
        )
