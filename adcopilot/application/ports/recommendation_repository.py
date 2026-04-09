"""RecommendationRepository port (Protocol)."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import Recommendation, RecommendationId, RecommendationStatus


class RecommendationRepository(Protocol):
    async def get(self, rec_id: RecommendationId) -> Recommendation | None: ...

    async def list_pending(self, account_id: AccountId) -> list[Recommendation]: ...

    async def save(self, rec: Recommendation) -> None: ...

    async def update_status(self, rec_id: RecommendationId, status: RecommendationStatus) -> None: ...

    async def update_explanation(self, rec_id: RecommendationId, explanation: str) -> None: ...
