"""Port for persisting PerformanceComparison entities."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.performance_tracking import PerformanceComparison
from adcopilot.domain.recommendation import RecommendationId


class PerformanceComparisonRepository(Protocol):
    async def save(self, comparison: PerformanceComparison) -> None: ...

    async def exists(self, recommendation_id: RecommendationId, window_days: int) -> bool: ...

    async def list_for_account(
        self, account_id: str, limit: int = 50
    ) -> list[PerformanceComparison]: ...
