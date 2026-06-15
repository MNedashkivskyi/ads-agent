"""Central entitlements: the single source of truth mapping every plan tier
to its capabilities and numeric account limit.

This module replaces the previously scattered and duplicated gating logic
(account-limit dicts in ``oauth.py`` / ``users.py`` and the inline STARTER
block in ``pmax.py``). Anything that needs to know "what can this plan do?"
or "how many accounts may this plan link?" must consult this module.

The contract here is asserted exactly by the parametrized matrix test and
mirrors Appendix A of the optimization pivot plan. Core features (nightly
audit and recommendations, approve/decline/undo, conversion-tracking audit,
Quality Score, search-term waste detection, spend-safety guardrails, the
performance dashboard) are intentionally *not* represented as capabilities:
they are ungated on every tier and must never be added to a gated set.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from adcopilot.domain.entities import PlanTier


class Capability(StrEnum):
    """Every gated capability in the product.

    Core features (audit, recommendations, approve/undo, conversion tracking,
    Quality Score, search-term waste, spend safety, dashboard) are ungated and
    deliberately absent from this enum.
    """

    MEASUREMENT_LOOP = "measurement_loop"
    AUDIENCES = "audiences"
    STRUCTURE_SEASONALITY = "structure_seasonality"
    AI_INSIGHTS = "ai_insights"
    AB_EXPERIMENTS = "ab_experiments"
    ADVANCED_OPTIMIZATION = "advanced_optimization"
    AUTO_APPLY = "auto_apply"
    PMAX_OPTIMIZATION = "pmax_optimization"
    CAUSAL_EXPERIMENTS = "causal_experiments"
    CROSS_ACCOUNT_REPORTS = "cross_account_reports"
    TEAM_SEATS = "team_seats"
    API_ACCESS = "api_access"


@dataclass(frozen=True)
class Entitlement:
    """The capabilities and account limit granted by a plan tier.

    ``max_accounts`` of ``None`` means unlimited (the Business tier).
    """

    max_accounts: int | None
    capabilities: frozenset[Capability]


# Professional unlocks the full optimization/automation surface.
_PROFESSIONAL_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        Capability.MEASUREMENT_LOOP,
        Capability.AUDIENCES,
        Capability.STRUCTURE_SEASONALITY,
        Capability.AI_INSIGHTS,
        Capability.AB_EXPERIMENTS,
        Capability.ADVANCED_OPTIMIZATION,
        Capability.AUTO_APPLY,
        Capability.PMAX_OPTIMIZATION,
    }
)

# Business adds the scale capabilities on top of everything Professional has.
_BUSINESS_CAPABILITIES: frozenset[Capability] = _PROFESSIONAL_CAPABILITIES | frozenset(
    {
        Capability.CAUSAL_EXPERIMENTS,
        Capability.CROSS_ACCOUNT_REPORTS,
        Capability.TEAM_SEATS,
        Capability.API_ACCESS,
    }
)


ENTITLEMENTS: dict[PlanTier, Entitlement] = {
    PlanTier.STARTER: Entitlement(max_accounts=1, capabilities=frozenset()),
    PlanTier.PROFESSIONAL: Entitlement(
        max_accounts=3, capabilities=_PROFESSIONAL_CAPABILITIES
    ),
    PlanTier.BUSINESS: Entitlement(
        max_accounts=None, capabilities=_BUSINESS_CAPABILITIES
    ),
}


def _entitlement(plan: PlanTier) -> Entitlement:
    # PlanTier.parse already collapses unknown values to STARTER, but guard the
    # lookup so a future tier without an entry degrades safely to most-restrictive.
    return ENTITLEMENTS.get(plan, ENTITLEMENTS[PlanTier.STARTER])


def has_capability(plan: PlanTier, capability: Capability) -> bool:
    """Whether ``plan`` is entitled to ``capability``."""
    return capability in _entitlement(plan).capabilities


def capabilities(plan: PlanTier) -> frozenset[Capability]:
    """The full capability set granted by ``plan``."""
    return _entitlement(plan).capabilities


def max_accounts(plan: PlanTier) -> int | None:
    """The maximum number of Google Ads accounts ``plan`` may link.

    Returns ``None`` for unlimited (Business).
    """
    return _entitlement(plan).max_accounts
