"""Port: Google Ads hourly metrics provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adcopilot.domain.entities import AccountId


@dataclass(frozen=True)
class HourlyMetric:
    """Aggregated metrics for a single calendar hour."""

    # ISO-8601 date string, e.g. "2026-04-16"
    date: str
    # 0-23 (account local time)
    hour: int
    spend_micros: int
    conversions: float
    impressions: int
    # Impression share ∈ [0.0, 1.0]; None when unavailable
    impression_share: float | None


@dataclass(frozen=True)
class ConversionTrackingStatus:
    has_errors: bool
    # Human-readable reason if has_errors is True
    error_detail: str | None


@dataclass(frozen=True)
class DailyBudgetStatus:
    """Snapshot of today's budget consumption."""

    # Total budget allocated for today (micros)
    daily_budget_micros: int
    # Amount spent so far today (micros)
    spent_today_micros: int
    # Percentage consumed: 0-100
    pct_consumed: float


class HourlyMetricsPort(Protocol):
    async def get_last_n_hours(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
        n: int,
    ) -> list[HourlyMetric]:
        """Return hourly aggregates for the last *n* complete hours."""
        ...

    async def get_baseline_for_hour(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
        hour_of_day: int,
        day_of_week: int,
        lookback_days: int = 7,
    ) -> HourlyMetric | None:
        """Return rolling average metric for the same hour+weekday over
        the last *lookback_days* days (skipping today)."""
        ...

    async def get_daily_budget_status(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
    ) -> list[DailyBudgetStatus]:
        """Return budget consumption status for each active campaign today."""
        ...

    async def get_conversion_tracking_status(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
    ) -> ConversionTrackingStatus:
        """Check whether any conversion tracking actions have errors."""
        ...

    async def get_impression_share_wow(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
    ) -> float | None:
        """Return week-over-week change in impression share.

        Returns a negative value if share dropped, e.g. -0.35 means -35 pp.
        Returns None when insufficient data.
        """
        ...
