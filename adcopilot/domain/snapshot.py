from dataclasses import dataclass
from datetime import date
from typing import NewType

from adcopilot.domain.entities import AccountId

SnapshotId = NewType("SnapshotId", str)


@dataclass(frozen=True)
class CampaignSnapshot:
    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    campaign_id: int
    name: str
    status: str
    channel_type: str
    budget_micros: int
    bidding_strategy: str
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float
    conv_value: float
    # Impression share metrics — None when the campaign has no search channel
    # data or insufficient impressions for Google to report the value.
    search_impression_share: float | None = None
    search_budget_lost_impression_share: float | None = None
    search_rank_lost_impression_share: float | None = None
    # Bidding target — only populated for TARGET_CPA campaigns; None otherwise.
    target_cpa_micros: int | None = None
    # All conversions (including view-through and cross-device); used by rule 39.
    all_conversions: float = 0.0


@dataclass(frozen=True)
class AssetGroupSnapshot:
    """One Performance Max / Shopping asset group on a snapshot date.

    `ad_strength` (POOR/AVERAGE/GOOD/EXCELLENT/UNSPECIFIED) and `primary_status`
    (ELIGIBLE/LIMITED/NOT_ELIGIBLE/PAUSED/REMOVED) drive the PMax health rules.
    """

    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    asset_group_id: int
    campaign_id: int
    name: str
    status: str
    ad_strength: str
    primary_status: str
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float
    conv_value: float


@dataclass(frozen=True)
class ListingGroupSnapshot:
    """One asset-group listing-group filter (product segmentation node)."""

    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    asset_group_id: int
    campaign_id: int
    listing_group_id: int
    dimension_type: str  # e.g. PRODUCT_CATEGORY, PRODUCT_BRAND, or "" for catch-all
    case_value: str  # the dimension value; empty for catch-all
    is_catch_all: bool


@dataclass(frozen=True)
class AdGroupSnapshot:
    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    ad_group_id: int
    campaign_id: int
    name: str
    status: str
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float


@dataclass(frozen=True)
class KeywordSnapshot:
    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    criterion_id: int
    ad_group_id: int
    text: str
    match_type: str
    status: str
    quality_score: int | None
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float
    ctr: float
    avg_cpc_micros: int
    expected_ctr: str | None = None
    ad_relevance: str | None = None
    landing_page_experience: str | None = None


@dataclass(frozen=True)
class SearchTermSnapshot:
    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    search_term: str
    ad_group_id: int
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float
    matched_keyword_id: int | None
    campaign_name: str = ""


@dataclass(frozen=True)
class AdSnapshot:
    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    ad_id: int
    ad_group_id: int
    type: str
    status: str
    headlines_json: str
    descriptions_json: str
    final_urls_json: str
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float
    # RSA ad strength reported by Google Ads (POOR / AVERAGE / GOOD / EXCELLENT).
    # None for non-RSA ad types or when Google hasn't evaluated the ad yet.
    ad_strength: str | None = None


@dataclass(frozen=True)
class DevicePerformanceSnapshot:
    """Daily performance metrics broken down by device (MOBILE, DESKTOP, TABLET, OTHER)."""

    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    campaign_id: int
    device: str  # MOBILE, DESKTOP, TABLET, OTHER, CONNECTED_TV
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float


@dataclass(frozen=True)
class GeoPerformanceSnapshot:
    """Daily performance metrics broken down by geographic location (criterion ID)."""

    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    campaign_id: int
    location_id: int  # Google Ads geo criterion ID
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float


@dataclass(frozen=True)
class HourPerformanceSnapshot:
    """Daily performance metrics broken down by hour of day (0-23)."""

    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    campaign_id: int
    hour_of_day: int  # 0-23
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float


@dataclass(frozen=True)
class DayOfWeekPerformanceSnapshot:
    """Daily performance metrics broken down by day of week."""

    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    campaign_id: int
    day_of_week: str  # MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float


@dataclass(frozen=True)
class AudiencePerformanceSnapshot:
    """Daily performance metrics for an observation audience in an ad group."""

    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    campaign_id: int
    ad_group_id: int
    criterion_id: int  # audience criterion ID
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float


@dataclass(frozen=True)
class NegativeKeywordSnapshot:
    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    criterion_id: int
    campaign_id: int
    # ad_group_id = 0 means this is a campaign-level negative keyword.
    # A non-zero value means it is scoped to that specific ad group.
    ad_group_id: int
    text: str
    match_type: str  # EXACT, PHRASE, or BROAD


@dataclass(frozen=True)
class ConversionActionSnapshot:
    """Account-level conversion action configuration.

    Fetched from the `conversion_action` GAQL resource (not a daily metric —
    it is account configuration), stored with snapshot_date for history.
    """

    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    conversion_action_id: int
    name: str
    # Category enum: PAGE_VIEW, PURCHASE, SIGNUP, LEAD, DOWNLOAD, DEFAULT, etc.
    category: str
    # ONE_PER_CLICK or MANY_PER_CLICK
    counting_type: str
    # ENABLED, REMOVED, or HIDDEN
    status: str
    # True = counts toward the "Conversions" column; False = "All conversions" only
    include_in_conversions_metric: bool
    # all_conversions metric over the last 7 days (0.0 when queried without metrics)
    all_conversions: float = 0.0


@dataclass(frozen=True)
class CampaignExtensionSnapshot:
    """Records which extension types are attached to a campaign.

    One row per (account, snapshot_date, campaign, extension_type).  Used by
    rules 41–43 to detect campaigns that are missing sitelinks, callouts, or
    structured snippets.
    """

    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    campaign_id: int
    # Extension type string: SITELINK, CALLOUT, STRUCTURED_SNIPPET, etc.
    extension_type: str


@dataclass(frozen=True)
class SitelinkPerformanceSnapshot:
    """Daily click + impression metrics for a single sitelink asset.

    One row per (account, snapshot_date, campaign_id, asset_id).  The rule
    engine loads a 30-day window, aggregates impressions/clicks per asset_id,
    and flags sitelinks with CTR < 0.5% and ≥500 impressions.
    """

    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    campaign_id: int
    asset_id: int
    impressions: int
    clicks: int


@dataclass(frozen=True)
class RemarketingListInfo:
    """Basic info about a Google Ads user list (remarketing audience).

    Used by Task 6.1/6.2 to check tag status and RLSA eligibility.
    """

    list_id: int
    name: str
    member_count: int
    """Approximate number of users in the list; -1 if still under threshold."""

    status: str
    """OPEN, CLOSED, or UNKNOWN."""
