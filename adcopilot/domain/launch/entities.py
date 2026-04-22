"""Domain entities for the campaign-launch feature.

Design rules
------------
- Pure Python only: no FastAPI, SQLAlchemy, or Google Ads imports.
- All value-object types are frozen dataclasses for structural immutability.
- Monetary PLN amounts are stored as ``Decimal``; micro-unit values (as used
  by the Google Ads API) are plain ``int``.
- Collection fields use ``list`` so callers can construct instances naturally;
  the frozen contract guarantees the *field reference* cannot be reassigned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import NewType

from adcopilot.domain.entities import AccountId, UserId

# ---------------------------------------------------------------------------
# Identity types
# ---------------------------------------------------------------------------

CampaignBriefId = NewType("CampaignBriefId", str)
CampaignProposalId = NewType("CampaignProposalId", str)

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class LaunchStatus(StrEnum):
    """Lifecycle states for a ``CampaignBrief``."""

    COLLECTING = "collecting"
    """Waiting for more information from the user."""

    GENERATING = "generating"
    """An LLM is currently producing the campaign proposal."""

    PROPOSED = "proposed"
    """A ``CampaignProposal`` has been generated and is awaiting review."""

    APPROVED = "approved"
    """The user has approved the proposal; awaiting creation in Google Ads."""

    CREATED_PAUSED = "created_paused"
    """Campaign created in Google Ads in a paused state."""

    ENABLED = "enabled"
    """Campaign is live and serving."""

    ABANDONED = "abandoned"
    """The user cancelled the launch flow."""


class MatchType(StrEnum):
    """Google Ads keyword match types."""

    BROAD = "broad"
    PHRASE = "phrase"
    EXACT = "exact"


# ---------------------------------------------------------------------------
# Leaf value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KeywordProposal:
    """A single proposed keyword inside an ad-group proposal."""

    text: str
    match_type: MatchType
    estimated_cpc_micros: int
    """Estimated cost-per-click in Google Ads micro-units (1 PLN = 1 000 000)."""


@dataclass(frozen=True)
class AdProposal:
    """A single proposed Responsive Search Ad (RSA)."""

    headlines: list[str]
    """Up to 15 headlines (Google Ads RSA limit)."""

    descriptions: list[str]
    """Up to 4 descriptions (Google Ads RSA limit)."""

    final_url: str
    """Landing-page URL."""

    path_segments: tuple[str, str]
    """The two display-path segments shown in the ad URL (path_1, path_2).
    Either or both may be empty strings."""


# ---------------------------------------------------------------------------
# Composite value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdGroupProposal:
    """A proposed ad group containing keywords and ads."""

    name: str
    keywords: list[KeywordProposal]
    ads: list[AdProposal]


# ---------------------------------------------------------------------------
# Extension value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SitelinkProposal:
    """A proposed sitelink extension."""

    link_text: str
    """≤25 characters."""

    description1: str
    """≤35 characters."""

    description2: str
    """≤35 characters."""

    final_url: str


@dataclass(frozen=True)
class CalloutProposal:
    """A proposed callout extension."""

    text: str
    """≤25 characters."""


@dataclass(frozen=True)
class StructuredSnippetProposal:
    """A proposed structured snippet extension."""

    header: str
    """e.g. "Services", "Types", "Brands"."""

    values: list[str]
    """3–10 values, each ≤25 characters."""


@dataclass(frozen=True)
class CampaignProposal:
    """The full campaign structure proposed by the AI for a given brief.

    One brief has at most one active proposal at a time (previous proposals
    are replaced when the brief is regenerated).
    """

    id: CampaignProposalId
    brief_id: CampaignBriefId
    campaign_name: str
    daily_budget_micros: int
    """Campaign daily budget in Google Ads micro-units."""

    location_targeting: str
    """Human-readable location name used for geo-targeting (e.g. "Warsaw, PL")."""

    bidding_strategy: str
    """Google Ads bidding strategy name (e.g. "TARGET_CPA", "MAXIMIZE_CONVERSIONS")."""

    ad_groups: list[AdGroupProposal]
    negative_keywords: list[str]
    """Campaign-level negative keywords (broad match by default)."""

    sitelinks: list[SitelinkProposal]
    """2–4 sitelink extensions."""

    callouts: list[CalloutProposal]
    """4–8 callout extensions."""

    structured_snippets: list[StructuredSnippetProposal]
    """1–2 structured snippet extensions."""

    estimated_cpc_range: tuple[int, int]
    """(min_micros, max_micros) estimated cost-per-click range across all keywords."""

    generated_at: datetime

    # Brand campaign fields — None/empty for MICRO tier
    brand_campaign_name: str | None = None
    """Separate Brand Search campaign name, e.g. 'MyBrand | Brand Search'."""

    brand_keywords: list[KeywordProposal] = None  # type: ignore[assignment]
    """Exact-match brand keywords (business name + variations). Empty for MICRO."""

    brand_daily_budget_micros: int = 0
    """Brand campaign daily budget (~10% of main). 0 for MICRO tier."""

    brand_ad: AdProposal | None = None
    """Single RSA for the brand ad group. None for MICRO tier."""

    def __post_init__(self) -> None:
        if self.brand_keywords is None:
            object.__setattr__(self, "brand_keywords", [])


# ---------------------------------------------------------------------------
# Root aggregate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CampaignBrief:
    """The user's intent for a new Google Ads campaign.

    Captures everything we need to generate a ``CampaignProposal``.
    This is the root aggregate for the launch bounded context.
    """

    id: CampaignBriefId
    user_id: UserId
    account_id: AccountId
    business_description: str
    """Free-text description of the business and its offering."""

    location: str
    """Geographic target of the campaign (city, region, or country)."""

    typical_customer_value: Decimal
    """Typical revenue per converted customer in PLN."""

    primary_action: str
    """The desired conversion action (e.g. "phone call", "form submission")."""

    monthly_budget_pln: Decimal
    """Total monthly budget the user is willing to spend, in PLN."""

    exclusions: list[str]
    """Topics, keywords, or audiences to exclude from the campaign."""

    language: str
    """ISO 639-1 language code for ad copy (e.g. "pl", "en")."""

    created_at: datetime
    status: LaunchStatus
    interview_step: int = 0
    """Which interview question we are currently waiting to receive.

    1 = waiting for Q1 (business description)
    2 = waiting for Q2 (location)
    3 = waiting for Q3 (typical customer value)
    4 = waiting for Q4 (primary action — collected via inline button)
    5 = waiting for Q5 (monthly budget)
    6 = waiting for Q6 (exclusions, optional)
    7 = all questions answered; summary displayed / proposal shown
    8 = awaiting revision text (user clicked "Make changes")
    0 = not yet started
    """

    campaign_resource_name: str | None = None
    """Google Ads campaign resource name, set after the campaign is created (PAUSED state)."""


# ---------------------------------------------------------------------------
# Performance Max campaign proposal (e-commerce with Merchant Center feed)
# ---------------------------------------------------------------------------

PMaxProposalId = NewType("PMaxProposalId", str)


@dataclass(frozen=True)
class AssetGroupProposal:
    """A Performance Max asset group (the PMax equivalent of an ad group)."""

    name: str
    headlines: list[str]
    """3–15 headlines for the asset group."""

    descriptions: list[str]
    """2–4 descriptions for the asset group."""

    final_url: str
    images_placeholder: list[str] = None  # type: ignore[assignment]
    """Placeholder paths for image assets — populated by the creative team."""

    def __post_init__(self) -> None:
        if self.images_placeholder is None:
            object.__setattr__(self, "images_placeholder", [])


@dataclass(frozen=True)
class PMaxCampaignProposal:
    """A Performance Max campaign proposal for e-commerce accounts with a Merchant Center feed.

    Uses broad audience signals and listing group filters (all products initially)
    rather than keywords.
    """

    id: PMaxProposalId
    brief_id: CampaignBriefId
    campaign_name: str
    daily_budget_micros: int
    merchant_center_feed_id: int
    """Linked Merchant Center account/feed ID."""

    asset_groups: list[AssetGroupProposal]
    """At least one asset group is required by the Google Ads API."""

    audience_signals: list[str] = None  # type: ignore[assignment]
    """In-market segment resource names as audience signals (best-effort)."""

    bidding_strategy: str = "MAXIMIZE_CONVERSIONS"
    generated_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.audience_signals is None:
            object.__setattr__(self, "audience_signals", [])
        if self.generated_at is None:
            from datetime import timezone
            object.__setattr__(self, "generated_at", datetime.now(tz=timezone.utc))


# ---------------------------------------------------------------------------
# Remarketing campaign proposal (Display, for GROWTH tier)
# ---------------------------------------------------------------------------

RemarketingProposalId = NewType("RemarketingProposalId", str)


@dataclass(frozen=True)
class RemarketingCampaignProposal:
    """A Display Remarketing campaign proposal generated for GROWTH-tier accounts.

    Separate from ``CampaignProposal`` because Display campaigns use audience
    targeting (user lists) rather than keywords, and Responsive Display Ads
    instead of RSAs.
    """

    id: RemarketingProposalId
    brief_id: CampaignBriefId
    campaign_name: str
    daily_budget_micros: int
    """15% of the original Search campaign's daily budget."""

    user_list_ids: list[int]
    """Remarketing list IDs to target (≥1,000 members each)."""

    bidding_strategy: str = "MAXIMIZE_CONVERSIONS"
    """Display remarketing converts well — start with MAXIMIZE_CONVERSIONS."""

    generated_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.generated_at is None:
            from datetime import timezone
            object.__setattr__(self, "generated_at", datetime.now(tz=timezone.utc))
