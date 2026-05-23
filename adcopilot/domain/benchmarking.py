"""Benchmarking domain entities — cross-account anonymized performance data."""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import NewType

BenchmarkId = NewType("BenchmarkId", str)

_MIN_ACCOUNTS = 5  # minimum cohort size for privacy


@dataclass(frozen=True)
class AccountMetrics:
    """Raw metrics for one account in a cohort (used only internally during aggregation)."""

    account_id: str
    cpa_micros: int            # 0 if no conversions
    ctr: float
    conversion_rate: float
    monthly_spend_micros: int


@dataclass(frozen=True)
class VerticalBenchmarkSnapshot:
    """Aggregated (anonymized) benchmark for a vertical × city_tier × week cohort."""

    id: BenchmarkId
    vertical: str
    city_tier: int             # 1 = major cities, 2 = regional, 3 = rest
    snapshot_week: date        # Monday of the ISO week
    account_count: int
    avg_cpa_micros: int
    median_cpa_micros: int
    p25_cpa_micros: int
    p75_cpa_micros: int
    avg_ctr: float
    avg_conversion_rate: float
    avg_monthly_spend_micros: int
    created_at: datetime

    @classmethod
    def aggregate(
        cls,
        vertical: str,
        city_tier: int,
        snapshot_week: date,
        accounts: list[AccountMetrics],
        created_at: datetime,
    ) -> VerticalBenchmarkSnapshot | None:
        """Return a snapshot if cohort ≥ MIN_ACCOUNTS; None otherwise (privacy guard)."""
        if len(accounts) < _MIN_ACCOUNTS:
            return None

        cpas = sorted(a.cpa_micros for a in accounts if a.cpa_micros > 0)
        if not cpas:
            return None

        n = len(cpas)
        p25 = cpas[max(0, int(n * 0.25) - 1)]
        median = cpas[n // 2]
        p75 = cpas[min(n - 1, int(n * 0.75))]

        return cls(
            id=BenchmarkId(str(uuid.uuid4())),
            vertical=vertical,
            city_tier=city_tier,
            snapshot_week=snapshot_week,
            account_count=len(accounts),
            avg_cpa_micros=int(statistics.mean(cpas)),
            median_cpa_micros=median,
            p25_cpa_micros=p25,
            p75_cpa_micros=p75,
            avg_ctr=statistics.mean(a.ctr for a in accounts),
            avg_conversion_rate=statistics.mean(a.conversion_rate for a in accounts),
            avg_monthly_spend_micros=int(
                statistics.mean(a.monthly_spend_micros for a in accounts)
            ),
            created_at=created_at,
        )
