"""Base types for the detection engine."""

from __future__ import annotations

from dataclasses import dataclass
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


class DetectionRule(Protocol):
    kind: RecommendationKind

    def detect(self, ctx: DetectionContext) -> list[Recommendation]: ...
