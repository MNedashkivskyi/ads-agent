"""hook_scorer — combine judge score, policy heuristic, and learned angle prior.

``final = judge × angle_prior × policy_multiplier``

* ``judge`` ∈ [0, 1] from the LLM judge (specificity/tension/pain-truth/clarity).
* ``angle_prior`` is the learned per-vertical weight (stubbed to 1.0 until Phase 6).
* ``policy_multiplier`` penalises risk without auto-dropping it: a HIGH-risk hook
  is dampened, not deleted — a bold, slightly-risky hook can still win if it's
  strong enough.

Pure and deterministic.
"""

from __future__ import annotations

from adcopilot.domain.campaign_intelligence.creatives.angle import Angle
from adcopilot.domain.campaign_intelligence.creatives.hook_candidate import HookCandidate
from adcopilot.domain.campaign_intelligence.creatives.hook_score import HookScore
from adcopilot.domain.campaign_intelligence.creatives.policy_risk import PolicyRisk

_POLICY_MULTIPLIER: dict[PolicyRisk, float] = {
    PolicyRisk.LOW: 1.0,
    PolicyRisk.MEDIUM: 0.85,
    PolicyRisk.HIGH: 0.5,  # penalised, never auto-dropped
}


def policy_multiplier(risk: PolicyRisk) -> float:
    return _POLICY_MULTIPLIER[risk]


def angle_prior_for(angle: Angle, learned_weights: dict[str, float] | None = None) -> float:
    if learned_weights and angle.value in learned_weights:
        return learned_weights[angle.value]
    return 1.0  # uniform stub until learned weights exist (Phase 6)


def compute_score(
    *,
    judge: float,
    risk: PolicyRisk,
    angle: Angle,
    learned_weights: dict[str, float] | None = None,
) -> HookScore:
    prior = angle_prior_for(angle, learned_weights)
    mult = policy_multiplier(risk)
    value = max(judge, 0.0) * prior * mult
    return HookScore(value=value, judge=judge, heuristic=mult, angle_prior=prior)


def score_candidate(
    candidate: HookCandidate,
    *,
    judge: float | None = None,
    learned_weights: dict[str, float] | None = None,
) -> HookScore:
    """Compute and attach the final score in place; return it."""
    judge_value = candidate.judge_score if judge is None else judge
    if judge_value is not None:
        candidate.judge_score = judge_value
    score = compute_score(
        judge=judge_value or 0.0,
        risk=candidate.policy.risk,
        angle=candidate.angle,
        learned_weights=learned_weights,
    )
    candidate.score = score
    return score
