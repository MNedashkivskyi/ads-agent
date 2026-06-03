"""Lifecycle use cases for native Google Ads campaign experiments (causal).

- propose_bidding_experiment: turn a bidding/tCPA change into a launched experiment
  (draft → apply change → experiment → schedule), human-approved, never auto-launched.
- decide_verdict: PURE — maps per-arm metrics + significance to a verdict.
- evaluate_campaign_experiment: read arm metrics, decide, persist if concluded.
- promote_experiment_outcome: on explicit approval, graduate a winner or end a loser.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog

from adcopilot.application.ports.experiment_mutations import ExperimentMutationsPort
from adcopilot.application.use_cases.evaluate_experiment import evaluate_experiment
from adcopilot.domain.campaign_experiment import (
    CampaignExperiment,
    ExperimentStatus,
    ExperimentVerdict,
)

logger = structlog.get_logger(__name__)

DEFAULT_DURATION_DAYS = 14
DEFAULT_CONFIDENCE_THRESHOLD = 0.95
DEFAULT_MIN_IMPRESSIONS = 1000


@dataclass
class VerdictDecision:
    concluded: bool
    verdict: ExperimentVerdict
    confidence: float | None
    reason: str


def decide_verdict(
    control_metrics: dict,
    treatment_metrics: dict,
    started_at: datetime,
    *,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    min_impressions: int = DEFAULT_MIN_IMPRESSIONS,
) -> VerdictDecision:
    """Pure: reuse the two-proportion z-test to grade a campaign experiment.

    `treatment` plays the role of the variant arm; if it wins significantly the
    change caused the lift (WIN), if control wins it's a LOSS, else INCONCLUSIVE.
    Returns concluded=False (verdict PENDING) while still underpowered/running.
    """
    result = evaluate_experiment(
        control_metrics=control_metrics,
        variant_metrics=treatment_metrics,
        min_impressions=min_impressions,
        confidence_threshold=confidence_threshold,
        started_at=started_at,
    )
    if not result.should_conclude:
        return VerdictDecision(False, ExperimentVerdict.PENDING, result.confidence, result.reason)
    if result.winner == "variant":
        verdict = ExperimentVerdict.WIN
    elif result.winner == "control":
        verdict = ExperimentVerdict.LOSS
    else:
        verdict = ExperimentVerdict.INCONCLUSIVE
    return VerdictDecision(True, verdict, result.confidence, result.reason)


async def propose_bidding_experiment(
    *,
    experiment: CampaignExperiment,
    adapter: ExperimentMutationsPort,
    refresh_token: str,
    customer_id: str,
    duration_days: int = DEFAULT_DURATION_DAYS,
    now: datetime | None = None,
) -> CampaignExperiment:
    """Launch a PROPOSED experiment on Google. Caller persists the result.

    Human-in-the-loop: only called after explicit approval. On any Google Ads
    failure the experiment is marked FAILED (surfaced to the user), not retried blindly.
    """
    started = now or datetime.now(UTC)
    name = f"adswise-exp-{experiment.change_kind.value.lower()}-{str(experiment.id)[:8]}"
    try:
        draft = await adapter.create_campaign_draft(
            refresh_token, customer_id, experiment.base_campaign_id, name
        )
        await adapter.apply_bidding_change_to_draft(
            refresh_token,
            customer_id,
            draft.draft_campaign_id,
            experiment.change_kind.value,
            experiment.change_payload,
        )
        exp_rn = await adapter.create_and_schedule_experiment(
            refresh_token,
            customer_id,
            experiment.base_campaign_id,
            draft,
            experiment.traffic_split,
            name,
            duration_days,
        )
    except Exception as exc:  # noqa: BLE001 — surface as FAILED, not silent
        experiment.mark_failed(str(exc))
        logger.warning("experiment_launch_failed", experiment_id=str(experiment.id), error=str(exc))
        return experiment

    experiment.mark_running(
        draft_resource_name=draft.draft_resource_name,
        experiment_resource_name=exp_rn,
        started_at=started,
        ends_at=started + timedelta(days=duration_days),
    )
    logger.info("experiment_launched", experiment_id=str(experiment.id), experiment=exp_rn)
    return experiment


async def evaluate_campaign_experiment(
    *,
    experiment: CampaignExperiment,
    adapter: ExperimentMutationsPort,
    refresh_token: str,
    customer_id: str,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    min_impressions: int = DEFAULT_MIN_IMPRESSIONS,
) -> VerdictDecision:
    """Read per-arm metrics, decide a verdict, and persist on the experiment if concluded."""
    if experiment.status is not ExperimentStatus.RUNNING or not experiment.experiment_resource_name:
        return VerdictDecision(False, ExperimentVerdict.PENDING, None, "not running")
    if experiment.started_at is None:
        return VerdictDecision(False, ExperimentVerdict.PENDING, None, "no start time")

    metrics = await adapter.get_experiment_metrics(
        refresh_token, customer_id, experiment.experiment_resource_name
    )
    decision = decide_verdict(
        metrics.control,
        metrics.treatment,
        experiment.started_at,
        confidence_threshold=confidence_threshold,
        min_impressions=min_impressions,
    )
    if decision.concluded:
        experiment.record_evaluation(
            control_metrics=metrics.control,
            treatment_metrics=metrics.treatment,
            verdict=decision.verdict,
            confidence=decision.confidence,
        )
    return decision


async def promote_experiment_outcome(
    *,
    experiment: CampaignExperiment,
    adapter: ExperimentMutationsPort,
    refresh_token: str,
    customer_id: str,
    promote: bool,
) -> CampaignExperiment:
    """Explicit, human-approved outcome: graduate a winner or end the experiment."""
    if not experiment.experiment_resource_name:
        experiment.mark_failed("no experiment resource to promote/end")
        return experiment
    try:
        if promote:
            if not experiment.is_promotable():
                raise ValueError("experiment is not a promotable WIN")
            await adapter.promote_experiment(
                refresh_token, customer_id, experiment.experiment_resource_name
            )
            experiment.mark_promoted()
        else:
            await adapter.end_experiment(
                refresh_token, customer_id, experiment.experiment_resource_name
            )
            experiment.mark_ended()
    except Exception as exc:  # noqa: BLE001
        experiment.mark_failed(str(exc))
        logger.warning("experiment_outcome_failed", experiment_id=str(experiment.id), error=str(exc))
    return experiment
