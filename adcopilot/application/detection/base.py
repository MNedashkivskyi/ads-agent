"""Base types for the detection engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from adcopilot.domain.entities import GoogleAdsAccount
from adcopilot.domain.recommendation import Recommendation, RecommendationKind
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    AudiencePerformanceSnapshot,
    CampaignSnapshot,
    DayOfWeekPerformanceSnapshot,
    DevicePerformanceSnapshot,
    GeoPerformanceSnapshot,
    HourPerformanceSnapshot,
    KeywordSnapshot,
    NegativeKeywordSnapshot,
    SearchTermSnapshot,
)


@dataclass
class HistoricalStats:
    """Aggregated stats for a look-back window (default 30 days)."""

    avg_cpa_micros: int
    total_cost_micros: int
    total_conversions: float
    days: int = 30


@dataclass
class DetectionContext:
    account: GoogleAdsAccount
    campaigns: list[CampaignSnapshot]
    ad_groups: list[AdGroupSnapshot]
    keywords: list[KeywordSnapshot]
    search_terms: list[SearchTermSnapshot]
    ads: list[AdSnapshot]
    history: HistoricalStats
    snapshot_date: date
    # 7-day-ago snapshots for week-over-week trend rules (Modules 1 & 2).
    # Empty lists when no historical data is available (e.g. first snapshot).
    prev_campaigns: list[CampaignSnapshot] = field(default_factory=list)
    prev_ad_groups: list[AdGroupSnapshot] = field(default_factory=list)
    prev_keywords: list[KeywordSnapshot] = field(default_factory=list)
    prev_ads: list[AdSnapshot] = field(default_factory=list)
    # Negative keywords (campaign-level and ad-group-level) for Module 3 conflict detection.
    negative_keywords: list[NegativeKeywordSnapshot] = field(default_factory=list)
    # 30-day targeting dimension performance data for Module 4 rules.
    # Empty lists when insufficient history exists (new accounts, first snapshot).
    device_performance: list[DevicePerformanceSnapshot] = field(default_factory=list)
    geo_performance: list[GeoPerformanceSnapshot] = field(default_factory=list)
    hour_performance: list[HourPerformanceSnapshot] = field(default_factory=list)
    day_of_week_performance: list[DayOfWeekPerformanceSnapshot] = field(default_factory=list)
    audience_performance: list[AudiencePerformanceSnapshot] = field(default_factory=list)


class DetectionRule(Protocol):
    kind: RecommendationKind

    def detect(self, ctx: DetectionContext) -> list[Recommendation]: ...
