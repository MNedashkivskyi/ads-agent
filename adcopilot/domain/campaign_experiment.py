"""Native Google Ads campaign-experiment domain (causal measurement).

Wraps an impactful change (first: bidding strategy / tCPA) as a real Google Ads
experiment — a CampaignDraft + Experiment with a traffic split — so the change's
lift is measured causally against a control arm, then promoted only if it wins.
This phase models the lifecycle; the adapter/use-cases drive it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class ExperimentChangeKind(str, Enum):
    BIDDING_STRATEGY = "BIDDING_STRATEGY"
    TARGET_CPA = "TARGET_CPA"
    TARGET_ROAS = "TARGET_ROAS"


class ExperimentStatus(str, Enum):
    PROPOSED = "PROPOSED"  # created locally, not yet launched on Google
    RUNNING = "RUNNING"  # draft + experiment created and scheduled
    EVALUATED = "EVALUATED"  # results read + verdict set
    PROMOTED = "PROMOTED"  # treatment graduated to the base campaign
    ENDED = "ENDED"  # ended without promotion
    FAILED = "FAILED"


class ExperimentVerdict(str, Enum):
    PENDING = "PENDING"
    WIN = "WIN"  # treatment beats control with significance
    LOSS = "LOSS"  # treatment worse / control better
    INCONCLUSIVE = "INCONCLUSIVE"  # no significant difference


@dataclass
class CampaignExperiment:
    account_id: str
    base_campaign_id: int
    change_kind: ExperimentChangeKind
    change_payload: dict  # e.g. {"bidding_strategy": "MAXIMIZE_CONVERSIONS"} or {"target_cpa_micros": 80000000}
    traffic_split: int = 50  # treatment %
    status: ExperimentStatus = ExperimentStatus.PROPOSED
    draft_resource_name: str | None = None
    experiment_resource_name: str | None = None
    started_at: datetime | None = None
    ends_at: datetime | None = None
    control_metrics: dict = field(default_factory=dict)
    treatment_metrics: dict = field(default_factory=dict)
    verdict: ExperimentVerdict = ExperimentVerdict.PENDING
    confidence: float | None = None
    evaluated_at: datetime | None = None
    last_error: str | None = None
    source_recommendation_id: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def mark_running(
        self,
        *,
        draft_resource_name: str,
        experiment_resource_name: str,
        started_at: datetime,
        ends_at: datetime,
    ) -> None:
        self.draft_resource_name = draft_resource_name
        self.experiment_resource_name = experiment_resource_name
        self.started_at = started_at
        self.ends_at = ends_at
        self.status = ExperimentStatus.RUNNING
        self.updated_at = datetime.now(UTC)

    def record_evaluation(
        self,
        *,
        control_metrics: dict,
        treatment_metrics: dict,
        verdict: ExperimentVerdict,
        confidence: float | None,
    ) -> None:
        self.control_metrics = control_metrics
        self.treatment_metrics = treatment_metrics
        self.verdict = verdict
        self.confidence = confidence
        self.status = ExperimentStatus.EVALUATED
        self.evaluated_at = datetime.now(UTC)
        self.updated_at = self.evaluated_at

    def mark_promoted(self) -> None:
        self.status = ExperimentStatus.PROMOTED
        self.updated_at = datetime.now(UTC)

    def mark_ended(self) -> None:
        self.status = ExperimentStatus.ENDED
        self.updated_at = datetime.now(UTC)

    def mark_failed(self, error: str) -> None:
        self.status = ExperimentStatus.FAILED
        self.last_error = error[:1000]
        self.updated_at = datetime.now(UTC)

    def is_promotable(self) -> bool:
        return self.status is ExperimentStatus.EVALUATED and self.verdict is ExperimentVerdict.WIN
