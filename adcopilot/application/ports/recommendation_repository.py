"""RecommendationRepository port (Protocol)."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationStatus,
)


class RecommendationRepository(Protocol):
    async def get(self, rec_id: RecommendationId) -> Recommendation | None: ...

    async def list_pending(self, account_id: AccountId) -> list[Recommendation]: ...

    async def list_active_dedup_keys(
        self, account_id: AccountId
    ) -> set[tuple[RecommendationKind, str]]: ...

    async def save(self, rec: Recommendation) -> None: ...

    async def update_status(
        self, rec_id: RecommendationId, status: RecommendationStatus
    ) -> None: ...

    async def expire_open_for_campaign(
        self, account_id: AccountId, campaign_id: int
    ) -> int: ...

    async def expire_pending_not_matching(
        self, account_id: AccountId, keep_keys: set[tuple[str, str]]
    ) -> int:
        """Expire PENDING recs whose (kind, target_hash) is not in keep_keys.

        Used after a detection run to drop suggestions that are no longer
        detected (the underlying issue was resolved). Returns the count expired.
        """
        ...

    async def update_explanation(self, rec_id: RecommendationId, explanation: str) -> None: ...

    async def list_executed_in_date_range(self, start: date, end: date) -> list[Recommendation]: ...
