"""CieDimensionPerformanceRepository — read/write learned dimension weights."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    DimensionPerformance,
)


class CieDimensionPerformanceRepository(Protocol):
    async def upsert(self, performance: DimensionPerformance) -> None:
        """Upsert by (vertical, dimension, value, language)."""
        ...

    async def get_map(
        self, *, vertical: str, dimension: str, language: str = "pl"
    ) -> dict[str, DimensionPerformance]:
        """value → DimensionPerformance for one (vertical, dimension, language)."""
        ...
