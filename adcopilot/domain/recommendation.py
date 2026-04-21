"""Recommendation domain model."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, NewType

from adcopilot.domain.entities import AccountId

RecommendationId = NewType("RecommendationId", str)


class RecommendationKind(Enum):
    # Module 0 — Hygiene
    ADD_NEGATIVE_KEYWORD = "ADD_NEGATIVE_KEYWORD"
    PAUSE_KEYWORD = "PAUSE_KEYWORD"
    PAUSE_AD = "PAUSE_AD"
    ADJUST_BUDGET = "ADJUST_BUDGET"
    ENABLE_CONVERSION_TRACKING = "ENABLE_CONVERSION_TRACKING"
    FIX_DISAPPROVED_AD = "FIX_DISAPPROVED_AD"
    CHANGE_MATCH_TYPE = "CHANGE_MATCH_TYPE"
    ADD_AD_VARIATION = "ADD_AD_VARIATION"
    INCREASE_BUDGET = "INCREASE_BUDGET"
    ADJUST_BIDDING_STRATEGY = "ADJUST_BIDDING_STRATEGY"
    # Module 1 — Performance degradation & trends
    CTR_DECLINE = "CTR_DECLINE"
    CPA_SPIKE = "CPA_SPIKE"
    CONVERSION_RATE_DROP = "CONVERSION_RATE_DROP"
    IMPRESSION_SHARE_EROSION = "IMPRESSION_SHARE_EROSION"
    SPEND_ACCELERATION = "SPEND_ACCELERATION"
    QUALITY_SCORE_DETERIORATION = "QUALITY_SCORE_DETERIORATION"
    # Module 2 — Ad copy & creative intelligence
    AD_KEYWORD_MISMATCH = "AD_KEYWORD_MISMATCH"
    MISSING_CTA = "MISSING_CTA"
    WEAK_RSA_STRENGTH = "WEAK_RSA_STRENGTH"
    AD_FATIGUE = "AD_FATIGUE"
    REDUNDANT_HEADLINES = "REDUNDANT_HEADLINES"
    GENERIC_DESCRIPTION = "GENERIC_DESCRIPTION"
    # Module 3 — Campaign structure & organisation
    OVERSTUFFED_AD_GROUP = "OVERSTUFFED_AD_GROUP"
    KEYWORD_CANNIBALIZATION = "KEYWORD_CANNIBALIZATION"
    NEGATIVE_KEYWORD_CONFLICT = "NEGATIVE_KEYWORD_CONFLICT"
    ORPHANED_CAMPAIGN = "ORPHANED_CAMPAIGN"
    MATCH_TYPE_REDUNDANCY = "MATCH_TYPE_REDUNDANCY"
    # Module 4 — Audience & targeting intelligence
    DEVICE_BID_ADJUSTMENT = "DEVICE_BID_ADJUSTMENT"
    GEO_EXCLUSION = "GEO_EXCLUSION"
    AD_SCHEDULE_ADJUSTMENT = "AD_SCHEDULE_ADJUSTMENT"
    DAY_OF_WEEK_BID_ADJUSTMENT = "DAY_OF_WEEK_BID_ADJUSTMENT"
    ADD_AUDIENCE_SIGNALS = "ADD_AUDIENCE_SIGNALS"
    # Module 5 — Budget & bidding strategy
    REALLOCATE_BUDGET = "REALLOCATE_BUDGET"
    IMPROVE_QUALITY_SCORE = "IMPROVE_QUALITY_SCORE"
    RELAX_TARGET_CPA = "RELAX_TARGET_CPA"
    DIVERSIFY_CHANNELS = "DIVERSIFY_CHANNELS"
    # Module 6 — Conversion tracking & measurement
    UPGRADE_CONVERSION_ACTION = "UPGRADE_CONVERSION_ACTION"
    DEDUPLICATE_CONVERSIONS = "DEDUPLICATE_CONVERSIONS"
    SET_CONVERSION_VALUE = "SET_CONVERSION_VALUE"
    # Module 7 — Ad extensions & assets
    ADD_SITELINKS = "ADD_SITELINKS"
    ADD_CALLOUTS = "ADD_CALLOUTS"
    ADD_STRUCTURED_SNIPPETS = "ADD_STRUCTURED_SNIPPETS"
    REFRESH_SITELINK = "REFRESH_SITELINK"
    # Module 8 — Landing page quality
    LANDING_PAGE_KEYWORD_MISMATCH = "LANDING_PAGE_KEYWORD_MISMATCH"


class RecommendationSeverity(Enum):
    CRITICAL = "CRITICAL"  # actively losing money now
    HIGH = "HIGH"          # significant savings/gain available
    MEDIUM = "MEDIUM"      # worth doing this week
    LOW = "LOW"            # nice to have


class RecommendationStatus(Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


# Kinds that have no Google Ads mutation executor — shown as advisory cards
# in Telegram with no Approve button to prevent runtime errors.
NON_EXECUTABLE_KINDS: frozenset[RecommendationKind] = frozenset(
    {
        # Module 0 — requires human action outside the system
        RecommendationKind.FIX_DISAPPROVED_AD,
        RecommendationKind.ADD_AD_VARIATION,
        RecommendationKind.ENABLE_CONVERSION_TRACKING,
        # Module 1 — trend alerts (informational)
        RecommendationKind.CTR_DECLINE,
        RecommendationKind.CPA_SPIKE,
        RecommendationKind.CONVERSION_RATE_DROP,
        RecommendationKind.IMPRESSION_SHARE_EROSION,
        RecommendationKind.SPEND_ACCELERATION,
        RecommendationKind.QUALITY_SCORE_DETERIORATION,
        # Module 2 — ad copy insights (informational)
        RecommendationKind.AD_KEYWORD_MISMATCH,
        RecommendationKind.MISSING_CTA,
        RecommendationKind.WEAK_RSA_STRENGTH,
        RecommendationKind.AD_FATIGUE,
        RecommendationKind.REDUNDANT_HEADLINES,
        RecommendationKind.GENERIC_DESCRIPTION,
        # Module 3 — structural issues (informational)
        RecommendationKind.OVERSTUFFED_AD_GROUP,
        RecommendationKind.KEYWORD_CANNIBALIZATION,
        RecommendationKind.NEGATIVE_KEYWORD_CONFLICT,
        RecommendationKind.ORPHANED_CAMPAIGN,
        RecommendationKind.MATCH_TYPE_REDUNDANCY,
        # Module 4 — targeting insights (informational)
        RecommendationKind.DAY_OF_WEEK_BID_ADJUSTMENT,
        RecommendationKind.ADD_AUDIENCE_SIGNALS,
        # Module 5 — budget/bidding insights (informational)
        RecommendationKind.IMPROVE_QUALITY_SCORE,
        RecommendationKind.RELAX_TARGET_CPA,
        RecommendationKind.DIVERSIFY_CHANNELS,
        # Module 6 — conversion tracking issues (informational)
        RecommendationKind.UPGRADE_CONVERSION_ACTION,
        RecommendationKind.DEDUPLICATE_CONVERSIONS,
        RecommendationKind.SET_CONVERSION_VALUE,
        # Module 7 — extension issues (ADD_SITELINKS/CALLOUTS/STRUCTURED_SNIPPETS are now executable)
        RecommendationKind.REFRESH_SITELINK,
        # Module 8 — landing page quality (informational, no Google Ads mutation)
        RecommendationKind.LANDING_PAGE_KEYWORD_MISMATCH,
    }
)


def compute_target_hash(target: dict[str, Any]) -> str:
    """Stable SHA-256 hex digest of the target dict for deduplication."""
    serialised = json.dumps(target, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialised.encode()).hexdigest()


def _new_recommendation_id() -> RecommendationId:
    return RecommendationId(str(uuid.uuid4()))


@dataclass(frozen=True)
class Recommendation:
    id: RecommendationId
    account_id: AccountId
    kind: RecommendationKind
    severity: RecommendationSeverity
    target: dict[str, Any]
    payload: dict[str, Any]
    estimated_monthly_savings_micros: int
    evidence: dict[str, Any]
    created_at: datetime
    status: RecommendationStatus
    explanation: str | None = None
    target_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.target_hash:
            object.__setattr__(self, "target_hash", compute_target_hash(self.target))
