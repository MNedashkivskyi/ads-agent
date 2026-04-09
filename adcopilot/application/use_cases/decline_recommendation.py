"""DeclineRecommendationUseCase: marks a recommendation as DECLINED."""

from __future__ import annotations

import structlog

from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.domain.recommendation import RecommendationId, RecommendationStatus

logger = structlog.get_logger(__name__)


class DeclineRecommendationUseCase:
    def __init__(self, rec_repo: RecommendationRepository) -> None:
        self._rec_repo = rec_repo

    async def execute(self, rec_id: RecommendationId) -> None:
        rec = await self._rec_repo.get(rec_id)
        if rec is None:
            raise ValueError(f"Recommendation {rec_id} not found")
        await self._rec_repo.update_status(rec_id, RecommendationStatus.DECLINED)
        logger.info("recommendation declined", rec_id=rec_id, kind=rec.kind.value)
