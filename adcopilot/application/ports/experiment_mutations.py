"""Port for native Google Ads campaign experiments (causal measurement).

Drafts + experiments are a high-stakes, multi-week write surface with no
validate_only; the adapter implementing this is validated live. Use cases depend
on this protocol so their lifecycle logic is fully testable with a fake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class DraftHandle:
    draft_resource_name: str
    draft_campaign_id: int


@dataclass
class ExperimentMetrics:
    """Per-arm metrics read back from a running/finished experiment."""

    status: str  # raw Google experiment status (e.g. SETUP, RUNNING, GRADUATED, ENDED)
    control: dict = field(default_factory=dict)  # {impressions, clicks, cost_micros, conversions, conversions_value}
    treatment: dict = field(default_factory=dict)


class ExperimentMutationsPort(Protocol):
    async def create_campaign_draft(
        self, refresh_token: str, customer_id: str, base_campaign_id: int, name: str
    ) -> DraftHandle: ...

    async def apply_bidding_change_to_draft(
        self,
        refresh_token: str,
        customer_id: str,
        draft_campaign_id: int,
        change_kind: str,
        change_payload: dict,
    ) -> None: ...

    async def create_and_schedule_experiment(
        self,
        refresh_token: str,
        customer_id: str,
        base_campaign_id: int,
        draft: DraftHandle,
        traffic_split: int,
        name: str,
        days: int,
    ) -> str:  # returns experiment_resource_name
        ...

    async def get_experiment_metrics(
        self, refresh_token: str, customer_id: str, experiment_resource_name: str
    ) -> ExperimentMetrics: ...

    async def promote_experiment(
        self, refresh_token: str, customer_id: str, experiment_resource_name: str
    ) -> None: ...

    async def end_experiment(
        self, refresh_token: str, customer_id: str, experiment_resource_name: str
    ) -> None: ...
