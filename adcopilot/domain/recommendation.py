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
