from __future__ import annotations

from datetime import UTC, datetime, timedelta

from adcopilot.domain.campaign_experiment import (
    CampaignExperiment,
    ExperimentChangeKind,
    ExperimentVerdict,
)
from adcopilot.interfaces.api.causal_experiments import _to_response


def test_to_response_maps_running_experiment() -> None:
    exp = CampaignExperiment(
        account_id="11111111-1111-1111-1111-111111111111",
        base_campaign_id=42,
        change_kind=ExperimentChangeKind.TARGET_CPA,
        change_payload={"target_cpa_micros": 80_000_000},
        traffic_split=50,
        source_recommendation_id="rec-1",
    )
    exp.mark_running(
        draft_resource_name="d",
        experiment_resource_name="customers/1/experiments/9",
        started_at=datetime(2026, 6, 3, tzinfo=UTC),
        ends_at=datetime(2026, 6, 17, tzinfo=UTC),
    )
    exp.record_evaluation(
        control_metrics={"conversions": 40},
        treatment_metrics={"conversions": 60},
        verdict=ExperimentVerdict.WIN,
        confidence=0.97,
    )

    resp = _to_response(exp)
    assert resp.base_campaign_id == 42
    assert resp.change_kind == "TARGET_CPA"
    assert resp.status == "EVALUATED"
    assert resp.verdict == "WIN"
    assert resp.confidence == 0.97
    assert resp.treatment_metrics["conversions"] == 60
    assert resp.source_recommendation_id == "rec-1"
    assert resp.started_at is not None
