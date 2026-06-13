"""Ports for performance attribution + the idempotent fact ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class PerformanceFact:
    """One attributed performance row for one entity on one day.

    ``dimension``/``value`` are the recovered strategic-dimension attribution
    (e.g. ``("angle", "PAIN")`` or ``("keyword_intent", "PROBLEM")``); both are
    ``None`` when the entity couldn't be attributed (still stored, for harvesting).
    """

    account_id: str
    customer_id: str
    entity_type: str  # "asset" | "keyword" | "search_term"
    entity_id: str
    day: date
    dimension: str | None
    value: str | None
    vertical: str
    language: str
    impressions: int
    clicks: int
    conversions: float
    cost_micros: int
    performance_label: str | None = None
    extra: dict | None = None


@dataclass(frozen=True)
class DimensionAggregate:
    """Summed metrics for one (vertical, dimension, value, language) group."""

    vertical: str
    dimension: str
    value: str
    language: str
    impressions: int
    clicks: int
    conversions: float


class CieAttributionRepository(Protocol):
    async def keyword_intent_map(self, account_id: str) -> dict[str, str]:
        """phrase (lower) → intent-type, from shipped keywords + candidates."""
        ...

    async def asset_angle_map(self, account_id: str) -> dict[str, str]:
        """asset text (lower) → angle, from shipped assets + hook candidates."""
        ...


class CiePerformanceFactRepository(Protocol):
    async def upsert_facts(self, facts: list[PerformanceFact]) -> int:
        """Idempotent upsert keyed by (account, entity_type, entity_id, day)."""
        ...

    async def aggregate_by_dimension(
        self, dimension: str
    ) -> list[DimensionAggregate]:
        """Aggregate all facts for a dimension into per-value groups (Phase 6)."""
        ...

    async def list_search_term_facts(
        self, account_id: str
    ) -> list[PerformanceFact]:
        """All search-term facts for an account (for harvesting, Phase 5)."""
        ...
