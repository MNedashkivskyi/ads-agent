"""Base types for the detection engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from adcopilot.domain.benchmarking import VerticalBenchmarkSnapshot
from adcopilot.domain.business_economics import BusinessEconomics
from adcopilot.domain.entities import GoogleAdsAccount
from adcopilot.domain.recommendation import Recommendation, RecommendationKind
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    AudiencePerformanceSnapshot,
    CampaignExtensionSnapshot,
    CampaignSnapshot,
    ConversionActionSnapshot,
    DayOfWeekPerformanceSnapshot,
    DevicePerformanceSnapshot,
    GeoPerformanceSnapshot,
    HourPerformanceSnapshot,
    KeywordSnapshot,
    NegativeKeywordSnapshot,
    SearchTermSnapshot,
    SitelinkPerformanceSnapshot,
)


@dataclass
class LandingPageData:
    """Scraped content from a landing page URL (for Rule 45)."""

    url: str
    reachable: bool
    page_title: str | None = None
    h1_text: str | None = None
    body_text_sample: str | None = None


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
    # Conversion action configuration for Module 6 rules.
    # Empty when not yet loaded or the account has no tracked conversions.
    conversion_actions: list[ConversionActionSnapshot] = field(default_factory=list)
    # Campaign extension types for Module 7 rules 41–43.
    # Empty when no extension data has been snapshotted yet.
    campaign_extensions: list[CampaignExtensionSnapshot] = field(default_factory=list)
    # Per-sitelink daily performance over a 30-day window for Module 7 rule 44.
    # Empty when no sitelink asset data exists.
    sitelink_performance: list[SitelinkPerformanceSnapshot] = field(default_factory=list)
    # Pre-fetched landing page content for Module 8 rule 45.
    # Keys are final_url strings; missing URL = rule skips that ad.
    landing_page_results: dict[str, LandingPageData] = field(default_factory=dict)
    # GA4 page metrics keyed by page_path — populated when GA4 is connected.
    ga4_page_metrics: dict[str, GA4PageMetrics] = field(default_factory=dict)
    # Auction insights rows for the past 14 days; empty when no data collected yet.
    # Each dict has: campaign_id, competitor_domain, impression_share, overlap_rate,
    # position_above_rate, snapshot_date.
    auction_insights: list[dict] = field(default_factory=list)
    # Latest vertical benchmark snapshot for Module 10 rule 48.
    # None when no benchmark exists yet for this account's vertical × city_tier.
    vertical_benchmark: VerticalBenchmarkSnapshot | None = field(default=None)
    # Per-account business economics for value-based rules (rule 40).
    # None when the user hasn't configured economics yet.
    business_economics: BusinessEconomics | None = field(default=None)


@dataclass
class GA4PageMetrics:
    page_path: str
    sessions: int
    bounce_rate: float | None
    avg_session_duration_sec: float | None
    pages_per_session: float | None


class DetectionRule(Protocol):
    kind: RecommendationKind

    def detect(self, ctx: DetectionContext) -> list[Recommendation]: ...
