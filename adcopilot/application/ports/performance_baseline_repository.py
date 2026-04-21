"""Port for persisting PerformanceBaseline entities."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.performance_tracking import PerformanceBaseline, PerformanceBaselineId
from adcopilot.domain.recommendation import RecommendationId


class PerformanceBaselineRepository(Protocol):
    async def save(self, baseline: PerformanceBaseline) -> None: ...

    async def get_by_recommendation(self, recommendation_id: RecommendationId) -> PerformanceBaseline | None: ...
