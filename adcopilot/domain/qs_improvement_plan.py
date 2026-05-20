"""Domain model for QS Improvement Plan."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, NewType

QSImprovementPlanId = NewType("QSImprovementPlanId", str)


class QSBottleneckComponent(Enum):
    AD_RELEVANCE = "AD_RELEVANCE"
    LANDING_PAGE_EXPERIENCE = "LANDING_PAGE_EXPERIENCE"
    EXPECTED_CTR = "EXPECTED_CTR"
    MIXED = "MIXED"


class QSActionType(Enum):
    REFRESH_AD_COPY = "REFRESH_AD_COPY"
    SCORE_LANDING_PAGE = "SCORE_LANDING_PAGE"
    TIGHTEN_MATCH_TYPE = "TIGHTEN_MATCH_TYPE"
    ADD_NEGATIVE = "ADD_NEGATIVE"
    CREATE_EXPERIMENT = "CREATE_EXPERIMENT"


class QSActionStatus(Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class QSPlanStatus(Enum):
    PROPOSED = "PROPOSED"
    IN_PROGRESS = "IN_PROGRESS"
    MEASURING = "MEASURING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class QSMetrics:
    avg_qs: float | None
    avg_cpc_micros: int | None
    avg_ctr: float | None


@dataclass
class QSAction:
    action_type: QSActionType
    status: QSActionStatus
    recommendation_id: str | None
    details_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class QSImprovementPlan:
    id: QSImprovementPlanId
    account_id: str
    keyword_criterion_ids: list[int]
    target_ad_group_resource_name: str | None
    current_avg_qs: float | None
    target_qs: float
    bottleneck_component: QSBottleneckComponent
    prescribed_actions: list[QSAction]
    status: QSPlanStatus
    baseline_metrics: QSMetrics | None
    current_metrics: QSMetrics | None
    evaluation_summary_pl: str | None
    created_at: datetime
    started_at: datetime | None
    measurement_ends_at: datetime | None
    completed_at: datetime | None
