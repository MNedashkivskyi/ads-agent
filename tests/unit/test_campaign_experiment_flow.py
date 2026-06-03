from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from adcopilot.application.ports.experiment_mutations import DraftHandle, ExperimentMetrics
from adcopilot.application.use_cases.campaign_experiment_flow import (
    decide_verdict,
    evaluate_campaign_experiment,
    promote_experiment_outcome,
    propose_bidding_experiment,
)
from adcopilot.domain.campaign_experiment import (
    CampaignExperiment,
    ExperimentChangeKind,
    ExperimentStatus,
    ExperimentVerdict,
)


def _exp(**kw) -> CampaignExperiment:
    return CampaignExperiment(
        account_id="11111111-1111-1111-1111-111111111111",
        base_campaign_id=100,
        change_kind=ExperimentChangeKind.TARGET_CPA,
        change_payload={"target_cpa_micros": 80_000_000},
        **kw,
    )


class FakeAdapter:
    def __init__(self, metrics: ExperimentMetrics | None = None, fail_on: str | None = None) -> None:
        self.metrics = metrics
        self.fail_on = fail_on
        self.calls: list[str] = []

    async def create_campaign_draft(self, rt, cid, base, name):
        self.calls.append("create_draft")
        if self.fail_on == "create_draft":
            raise RuntimeError("draft boom")
        return DraftHandle(draft_resource_name=f"customers/{cid}/campaignDrafts/{base}~5", draft_campaign_id=555)

    async def apply_bidding_change_to_draft(self, rt, cid, draft_cid, kind, payload):
        self.calls.append("apply_change")

    async def create_and_schedule_experiment(self, rt, cid, base, draft, split, name, days):
        self.calls.append("create_experiment")
        return f"customers/{cid}/experiments/77"

    async def get_experiment_metrics(self, rt, cid, exp_rn):
        self.calls.append("get_metrics")
        return self.metrics

    async def promote_experiment(self, rt, cid, exp_rn):
        self.calls.append("promote")

    async def end_experiment(self, rt, cid, exp_rn):
        self.calls.append("end")


# ---- decide_verdict (pure) ----

def test_decide_verdict_treatment_wins() -> None:
    started = datetime.now(UTC) - timedelta(days=10)
    d = decide_verdict(
        control_metrics={"impressions": 5000, "conversions": 40},
        treatment_metrics={"impressions": 5000, "conversions": 120},
        started_at=started,
        min_impressions=1000,
    )
    assert d.concluded is True
    assert d.verdict is ExperimentVerdict.WIN


def test_decide_verdict_control_wins_is_loss() -> None:
    started = datetime.now(UTC) - timedelta(days=10)
    d = decide_verdict(
        control_metrics={"impressions": 5000, "conversions": 150},
        treatment_metrics={"impressions": 5000, "conversions": 30},
        started_at=started,
        min_impressions=1000,
    )
    assert d.concluded is True
    assert d.verdict is ExperimentVerdict.LOSS


def test_decide_verdict_underpowered_stays_pending() -> None:
    started = datetime.now(UTC) - timedelta(days=2)
    d = decide_verdict(
        control_metrics={"impressions": 100, "conversions": 1},
        treatment_metrics={"impressions": 100, "conversions": 2},
        started_at=started,
        min_impressions=1000,
    )
    assert d.concluded is False
    assert d.verdict is ExperimentVerdict.PENDING


# ---- propose ----

@pytest.mark.asyncio
async def test_propose_launches_and_marks_running() -> None:
    adapter = FakeAdapter()
    exp = _exp()
    result = await propose_bidding_experiment(
        experiment=exp, adapter=adapter, refresh_token="rt", customer_id="123", duration_days=14
    )
    assert result.status is ExperimentStatus.RUNNING
    assert result.experiment_resource_name == "customers/123/experiments/77"
    assert result.ends_at is not None and result.started_at is not None
    assert (result.ends_at - result.started_at).days == 14
    assert adapter.calls == ["create_draft", "apply_change", "create_experiment"]


@pytest.mark.asyncio
async def test_propose_failure_marks_failed_not_running() -> None:
    adapter = FakeAdapter(fail_on="create_draft")
    exp = _exp()
    result = await propose_bidding_experiment(
        experiment=exp, adapter=adapter, refresh_token="rt", customer_id="123"
    )
    assert result.status is ExperimentStatus.FAILED
    assert "draft boom" in (result.last_error or "")


# ---- evaluate ----

@pytest.mark.asyncio
async def test_evaluate_records_verdict_when_concluded() -> None:
    adapter = FakeAdapter(
        metrics=ExperimentMetrics(
            status="RUNNING",
            control={"impressions": 5000, "conversions": 40},
            treatment={"impressions": 5000, "conversions": 120},
        )
    )
    exp = _exp()
    exp.mark_running(
        draft_resource_name="d",
        experiment_resource_name="customers/123/experiments/77",
        started_at=datetime.now(UTC) - timedelta(days=10),
        ends_at=datetime.now(UTC) + timedelta(days=4),
    )
    decision = await evaluate_campaign_experiment(
        experiment=exp, adapter=adapter, refresh_token="rt", customer_id="123"
    )
    assert decision.concluded is True
    assert exp.status is ExperimentStatus.EVALUATED
    assert exp.verdict is ExperimentVerdict.WIN


@pytest.mark.asyncio
async def test_evaluate_skips_non_running() -> None:
    adapter = FakeAdapter()
    exp = _exp()  # PROPOSED
    decision = await evaluate_campaign_experiment(
        experiment=exp, adapter=adapter, refresh_token="rt", customer_id="123"
    )
    assert decision.concluded is False
    assert "get_metrics" not in adapter.calls


# ---- promote/end ----

@pytest.mark.asyncio
async def test_promote_winner() -> None:
    adapter = FakeAdapter()
    exp = _exp()
    exp.mark_running(
        draft_resource_name="d", experiment_resource_name="customers/123/experiments/77",
        started_at=datetime.now(UTC) - timedelta(days=14), ends_at=datetime.now(UTC),
    )
    exp.record_evaluation(control_metrics={}, treatment_metrics={}, verdict=ExperimentVerdict.WIN, confidence=0.99)
    result = await promote_experiment_outcome(
        experiment=exp, adapter=adapter, refresh_token="rt", customer_id="123", promote=True
    )
    assert result.status is ExperimentStatus.PROMOTED
    assert "promote" in adapter.calls


@pytest.mark.asyncio
async def test_promote_non_winner_fails() -> None:
    adapter = FakeAdapter()
    exp = _exp()
    exp.mark_running(
        draft_resource_name="d", experiment_resource_name="customers/123/experiments/77",
        started_at=datetime.now(UTC) - timedelta(days=14), ends_at=datetime.now(UTC),
    )
    exp.record_evaluation(control_metrics={}, treatment_metrics={}, verdict=ExperimentVerdict.LOSS, confidence=0.1)
    result = await promote_experiment_outcome(
        experiment=exp, adapter=adapter, refresh_token="rt", customer_id="123", promote=True
    )
    assert result.status is ExperimentStatus.FAILED
    assert "promote" not in adapter.calls


@pytest.mark.asyncio
async def test_end_experiment() -> None:
    adapter = FakeAdapter()
    exp = _exp()
    exp.mark_running(
        draft_resource_name="d", experiment_resource_name="customers/123/experiments/77",
        started_at=datetime.now(UTC) - timedelta(days=14), ends_at=datetime.now(UTC),
    )
    exp.record_evaluation(control_metrics={}, treatment_metrics={}, verdict=ExperimentVerdict.INCONCLUSIVE, confidence=0.5)
    result = await promote_experiment_outcome(
        experiment=exp, adapter=adapter, refresh_token="rt", customer_id="123", promote=False
    )
    assert result.status is ExperimentStatus.ENDED
    assert "end" in adapter.calls
