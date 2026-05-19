"""EvaluateExperimentUseCase — z-test for two-proportion conversion rate comparison."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import structlog

logger = structlog.get_logger(__name__)

Winner = Literal["control", "variant", "inconclusive"]

_MAX_DAYS = 30


@dataclass
class EvaluationResult:
    should_conclude: bool
    winner: Winner
    p_value: float | None
    confidence: float | None
    reason: str


def _two_proportion_z_test(
    conversions_a: float,
    impressions_a: float,
    conversions_b: float,
    impressions_b: float,
) -> float | None:
    """Return two-tailed p-value for H0: rate_a == rate_b. Returns None when underpowered."""
    if impressions_a < 1 or impressions_b < 1:
        return None
    p_a = conversions_a / impressions_a
    p_b = conversions_b / impressions_b
    p_pool = (conversions_a + conversions_b) / (impressions_a + impressions_b)
    if p_pool == 0 or p_pool == 1:
        return None
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / impressions_a + 1 / impressions_b))
    if se == 0:
        return None
    z = (p_a - p_b) / se
    # Two-tailed p-value approximation (error function)
    p = 2 * (1 - _norm_cdf(abs(z)))
    return p


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via math.erf."""
    return (1 + math.erf(x / math.sqrt(2))) / 2


def evaluate_experiment(
    control_metrics: dict,
    variant_metrics: dict,
    min_impressions: int,
    confidence_threshold: float,
    started_at: datetime,
) -> EvaluationResult:
    ctrl_imp = float(control_metrics.get("impressions", 0))
    var_imp = float(variant_metrics.get("impressions", 0))
    ctrl_conv = float(control_metrics.get("conversions", 0))
    var_conv = float(variant_metrics.get("conversions", 0))

    days_running = (datetime.now(UTC) - started_at).days

    # Auto-conclude as inconclusive after max days regardless of results
    if days_running >= _MAX_DAYS:
        return EvaluationResult(
            should_conclude=True,
            winner="inconclusive",
            p_value=None,
            confidence=None,
            reason=f"Max duration ({_MAX_DAYS}d) reached without significance",
        )

    # Not enough impressions yet
    if ctrl_imp < min_impressions or var_imp < min_impressions:
        return EvaluationResult(
            should_conclude=False,
            winner="inconclusive",
            p_value=None,
            confidence=None,
            reason=f"Insufficient impressions: control={ctrl_imp:.0f}, variant={var_imp:.0f}",
        )

    p_value = _two_proportion_z_test(ctrl_conv, ctrl_imp, var_conv, var_imp)
    if p_value is None:
        return EvaluationResult(
            should_conclude=False,
            winner="inconclusive",
            p_value=None,
            confidence=None,
            reason="Cannot compute significance (zero rate in one arm)",
        )

    confidence = 1 - p_value
    alpha = 1 - confidence_threshold

    if p_value >= alpha:
        return EvaluationResult(
            should_conclude=False,
            winner="inconclusive",
            p_value=p_value,
            confidence=confidence,
            reason=f"Not yet significant (p={p_value:.3f}, need p<{alpha:.3f})",
        )

    # Significant result — pick winner by conversion rate
    ctrl_rate = ctrl_conv / ctrl_imp if ctrl_imp > 0 else 0
    var_rate = var_conv / var_imp if var_imp > 0 else 0
    winner: Winner = "variant" if var_rate > ctrl_rate else "control"

    return EvaluationResult(
        should_conclude=True,
        winner=winner,
        p_value=p_value,
        confidence=confidence,
        reason=f"Significant at p={p_value:.3f}. {winner} wins (ctrl={ctrl_rate:.3%}, var={var_rate:.3%})",
    )
