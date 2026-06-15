"""Auto-apply domain logic — which recommendations may be executed automatically.

Auto-apply (Phase 3 / T3.1) lets Professional+ accounts opt in to having
*low-risk* recommendations executed without manual approval, within
spend-safety guardrails. This module is the single source of truth for what
"low-risk" means and is pure (no I/O) so it can be unit-tested exhaustively.

Safety posture:
- Only an explicit allow-list of reversible, spend-reducing kinds is eligible.
  Anything that can *increase* spend (budget/bid increases, target-CPA/ROAS
  relaxation) is never eligible, regardless of settings.
- Severity must be within the account's configured ceiling.
- The per-day change cap bounds how many auto-applies can run per account/day.
- The SpendGuard preventive check still runs at execution time (enforced by
  ExecuteRecommendationUseCase) — this module only decides eligibility.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from adcopilot.domain.recommendation import (
    NON_EXECUTABLE_KINDS,
    Recommendation,
    RecommendationKind,
    RecommendationSeverity,
)


class AutoApplyRisk(Enum):
    """Coarse risk tier used to bound which recommendations may auto-apply."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"


# Reversible, spend-reducing or spend-neutral kinds that are safe to auto-apply.
# Deliberately conservative: adding negatives and pausing individual wasteful
# keywords reduce wasted spend and are easily reversed. Pausing whole
# campaigns/ads, any budget/bid increase, bidding-strategy or target changes,
# and creative generation are intentionally excluded.
_LOW_RISK_KINDS: frozenset[RecommendationKind] = frozenset(
    {
        RecommendationKind.ADD_NEGATIVE_KEYWORD,
        RecommendationKind.PAUSE_KEYWORD,
        RecommendationKind.NEGATIVE_KEYWORD_CONFLICT,
    }
)

# Kinds that can raise spend — never auto-applied (defence-in-depth; none of
# these are in the low-risk set above, but this makes the intent explicit).
_SPEND_INCREASING_KINDS: frozenset[RecommendationKind] = frozenset(
    {
        RecommendationKind.INCREASE_BUDGET,
        RecommendationKind.ADJUST_BUDGET,
        RecommendationKind.REALLOCATE_BUDGET,
        RecommendationKind.ADJUST_BIDDING_STRATEGY,
        RecommendationKind.RELAX_TARGET_CPA,
        RecommendationKind.ADJUST_PMAX_TARGET_ROAS,
        RecommendationKind.AUDIENCE_BID_ADJUSTMENT,
        RecommendationKind.DEVICE_BID_ADJUSTMENT,
        RecommendationKind.DAY_OF_WEEK_BID_ADJUSTMENT,
    }
)

# Mapping from risk tier to the set of kinds it permits. MEDIUM is a superset of
# LOW; today they are identical because the safe-list is already conservative —
# the tier exists so the ceiling can be widened later without touching callers.
_RISK_KINDS: dict[AutoApplyRisk, frozenset[RecommendationKind]] = {
    AutoApplyRisk.LOW: _LOW_RISK_KINDS,
    AutoApplyRisk.MEDIUM: _LOW_RISK_KINDS,
}

# Severities permitted to auto-apply. CRITICAL is excluded: a critical issue
# warrants a human look even when auto-apply is on.
_ALLOWED_SEVERITIES: frozenset[RecommendationSeverity] = frozenset(
    {
        RecommendationSeverity.LOW,
        RecommendationSeverity.MEDIUM,
        RecommendationSeverity.HIGH,
    }
)


def is_auto_appliable(
    kind: RecommendationKind,
    severity: RecommendationSeverity,
    max_risk: AutoApplyRisk = AutoApplyRisk.LOW,
) -> bool:
    """Whether a recommendation of this kind/severity may be auto-applied.

    Eligible only when the kind is in the allow-list for ``max_risk``, is not a
    spend-increasing kind, is executable (has a Google Ads mutation executor),
    and the severity is within the allowed band.
    """
    if kind in NON_EXECUTABLE_KINDS:
        return False
    if kind in _SPEND_INCREASING_KINDS:
        return False
    if severity not in _ALLOWED_SEVERITIES:
        return False
    return kind in _RISK_KINDS.get(max_risk, frozenset())


@dataclass(frozen=True)
class AutoApplySettings:
    """Per-account auto-apply configuration."""

    enabled: bool = False
    max_risk: AutoApplyRisk = AutoApplyRisk.LOW
    max_changes_per_day: int = 5


def select_for_auto_apply(
    recommendations: Iterable[Recommendation],
    settings: AutoApplySettings,
    *,
    already_applied_today: int = 0,
) -> list[Recommendation]:
    """Pick the recommendations to auto-apply, honouring the daily cap.

    Pure: returns the eligible subset (in input order) bounded by the remaining
    daily budget. ``already_applied_today`` lets the caller account for
    auto-applies that already ran today so the cap is respected across runs.
    Returns an empty list when auto-apply is disabled.
    """
    if not settings.enabled:
        return []
    remaining = settings.max_changes_per_day - already_applied_today
    if remaining <= 0:
        return []

    eligible: list[Recommendation] = []
    for rec in recommendations:
        if is_auto_appliable(rec.kind, rec.severity, settings.max_risk):
            eligible.append(rec)
            if len(eligible) >= remaining:
                break
    return eligible


def parse_risk(value: str | None) -> AutoApplyRisk:
    """Tolerantly coerce a stored/inbound risk string to an AutoApplyRisk."""
    if not value:
        return AutoApplyRisk.LOW
    try:
        return AutoApplyRisk(value.strip().upper())
    except ValueError:
        return AutoApplyRisk.LOW


__all__ = [
    "AutoApplyRisk",
    "AutoApplySettings",
    "is_auto_appliable",
    "parse_risk",
    "select_for_auto_apply",
]
