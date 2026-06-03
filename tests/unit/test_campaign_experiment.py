from __future__ import annotations

from datetime import UTC, datetime

from adcopilot.domain.campaign_experiment import (
    CampaignExperiment,
    ExperimentChangeKind,
    ExperimentStatus,
    ExperimentVerdict,
)


def _exp() -> CampaignExperiment:
    return CampaignExperiment(
        account_id="acc-1",
        base_campaign_id=123,
        change_kind=ExperimentChangeKind.BIDDING_STRATEGY,
        change_payload={"bidding_strategy": "MAXIMIZE_CONVERSIONS"},
    )


def test_lifecycle_transitions() -> None:
    e = _exp()
    assert e.status is ExperimentStatus.PROPOSED
    assert e.verdict is ExperimentVerdict.PENDING
    assert e.is_promotable() is False

    e.mark_running(
        draft_resource_name="customers/1/campaignDrafts/1~2",
        experiment_resource_name="customers/1/experiments/9",
        started_at=datetime(2026, 6, 3, tzinfo=UTC),
        ends_at=datetime(2026, 6, 17, tzinfo=UTC),
    )
    assert e.status is ExperimentStatus.RUNNING

    e.record_evaluation(
        control_metrics={"conversions": 40, "impressions": 5000},
        treatment_metrics={"conversions": 60, "impressions": 5000},
        verdict=ExperimentVerdict.WIN,
        confidence=0.97,
    )
    assert e.status is ExperimentStatus.EVALUATED
    assert e.is_promotable() is True
    assert e.confidence == 0.97


def test_loss_not_promotable() -> None:
    e = _exp()
    e.mark_running(
        draft_resource_name="d", experiment_resource_name="x",
        started_at=datetime(2026, 6, 3, tzinfo=UTC), ends_at=datetime(2026, 6, 17, tzinfo=UTC),
    )
    e.record_evaluation(control_metrics={}, treatment_metrics={}, verdict=ExperimentVerdict.LOSS, confidence=0.2)
    assert e.is_promotable() is False
    e.mark_ended()
    assert e.status is ExperimentStatus.ENDED


def test_mark_failed_records_error() -> None:
    e = _exp()
    e.mark_failed("draft creation failed")
    assert e.status is ExperimentStatus.FAILED
    assert "draft creation failed" in (e.last_error or "")
