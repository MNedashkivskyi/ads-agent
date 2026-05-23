"""SnoozeRecommendationUseCase: snoozes a recommendation for N days."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog

from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.application.ports.snooze_repository import SnoozeRepository
from adcopilot.domain.recommendation import RecommendationId

logger = structlog.get_logger(__name__)

_DEFAULT_SNOOZE_DAYS = 7


class SnoozeRecommendationUseCase:
    def __init__(self, rec_repo: RecommendationRepository, snooze_repo: SnoozeRepository) -> None:
        self._rec_repo = rec_repo
        self._snooze_repo = snooze_repo

    async def execute(
        self, rec_id: RecommendationId, snooze_days: int = _DEFAULT_SNOOZE_DAYS
    ) -> datetime:
        """Snooze the recommendation and return the snoozed_until timestamp."""
        rec = await self._rec_repo.get(rec_id)
        if rec is None:
            raise ValueError(f"Recommendation {rec_id} not found")
        snoozed_until = datetime.now(UTC) + timedelta(days=snooze_days)
        await self._snooze_repo.save_snooze(rec, snoozed_until)
        logger.info(
            "recommendation snoozed",
            rec_id=rec_id,
            kind=rec.kind.value,
            snoozed_until=snoozed_until.isoformat(),
        )
        return snoozed_until
