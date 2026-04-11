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
    CampaignSnapshot,
    KeywordSnapshot,
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
    # 7-day-ago snapshots for week-over-week trend rules (Module 1).
    # Empty lists when no historical data is available (e.g. first snapshot).
    prev_campaigns: list[CampaignSnapshot] = field(default_factory=list)
    prev_ad_groups: list[AdGroupSnapshot] = field(default_factory=list)
    prev_keywords: list[KeywordSnapshot] = field(default_factory=list)


class DetectionRule(Protocol):
    kind: RecommendationKind

    def detect(self, ctx: DetectionContext) -> list[Recommendation]: ...
