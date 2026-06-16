"""Matrix test for the central entitlements module.

Asserts, per tier, the exact capability set and account limit defined in
Appendix A of the optimization pivot plan. If any tier's capabilities or
limit drift, this test fails — that is the whole point.
"""

from __future__ import annotations

import pytest

from adcopilot.application.entitlements import (
    Capability,
    capabilities,
    has_capability,
    max_accounts,
)
from adcopilot.domain.entities import PlanTier

# Appendix A, transcribed exactly. This is the contract.
_EXPECTED_CAPABILITIES: dict[PlanTier, set[Capability]] = {
    PlanTier.STARTER: set(),
    PlanTier.PROFESSIONAL: {
        Capability.MEASUREMENT_LOOP,
        Capability.AUDIENCES,
        Capability.STRUCTURE_SEASONALITY,
        Capability.AI_INSIGHTS,
        Capability.AB_EXPERIMENTS,
        Capability.ADVANCED_OPTIMIZATION,
        Capability.AUTO_APPLY,
        Capability.PMAX_OPTIMIZATION,
    },
    PlanTier.BUSINESS: {
        Capability.MEASUREMENT_LOOP,
        Capability.AUDIENCES,
        Capability.STRUCTURE_SEASONALITY,
        Capability.AI_INSIGHTS,
        Capability.AB_EXPERIMENTS,
        Capability.ADVANCED_OPTIMIZATION,
        Capability.AUTO_APPLY,
        Capability.PMAX_OPTIMIZATION,
        Capability.CAUSAL_EXPERIMENTS,
        Capability.CROSS_ACCOUNT_REPORTS,
        Capability.TEAM_SEATS,
        Capability.API_ACCESS,
    },
}

_EXPECTED_MAX_ACCOUNTS: dict[PlanTier, int | None] = {
    PlanTier.STARTER: 1,
    PlanTier.PROFESSIONAL: 3,
    PlanTier.BUSINESS: None,
}


@pytest.mark.parametrize("plan", list(PlanTier))
def test_capability_set_matches_appendix_a(plan: PlanTier) -> None:
    assert set(capabilities(plan)) == _EXPECTED_CAPABILITIES[plan]


@pytest.mark.parametrize("plan", list(PlanTier))
def test_max_accounts_matches_appendix_a(plan: PlanTier) -> None:
    assert max_accounts(plan) == _EXPECTED_MAX_ACCOUNTS[plan]


def test_spot_checks_from_plan() -> None:
    assert has_capability(PlanTier.STARTER, Capability.AUDIENCES) is False
    assert has_capability(PlanTier.PROFESSIONAL, Capability.AUDIENCES) is True
    assert has_capability(PlanTier.PROFESSIONAL, Capability.CAUSAL_EXPERIMENTS) is False
    assert has_capability(PlanTier.BUSINESS, Capability.CAUSAL_EXPERIMENTS) is True


def test_business_is_unlimited() -> None:
    assert max_accounts(PlanTier.BUSINESS) is None


def test_business_superset_of_professional() -> None:
    assert capabilities(PlanTier.PROFESSIONAL) <= capabilities(PlanTier.BUSINESS)


# ---------------------------------------------------------------------------
# T6.3 — lock the model so it cannot drift silently.
# ---------------------------------------------------------------------------

# The complete set of gated capabilities (Appendix A). If a capability is added
# or removed, this test must be updated deliberately — that is the gate.
_APPENDIX_A_CAPABILITIES: set[str] = {
    "measurement_loop",
    "audiences",
    "structure_seasonality",
    "ai_insights",
    "ab_experiments",
    "advanced_optimization",
    "auto_apply",
    "pmax_optimization",
    "causal_experiments",
    "cross_account_reports",
    "team_seats",
    "api_access",
}

# Core features stay ungated on every tier — they must never become capabilities.
_CORE_FEATURES_NEVER_GATED: set[str] = {
    "recommendations",
    "conversion_tracking",
    "quality_score",
    "search_term_waste",
    "spend_safety",
    "dashboard",
    "approve",
    "undo",
}


def test_capability_enum_is_exactly_appendix_a() -> None:
    """The Capability enum must equal Appendix A exactly — no extra, none missing."""
    assert {c.value for c in Capability} == _APPENDIX_A_CAPABILITIES


def test_core_features_are_not_capabilities() -> None:
    """Core features must never leak into the gated capability set (T6.3)."""
    gated = {c.value for c in Capability}
    assert gated.isdisjoint(_CORE_FEATURES_NEVER_GATED)


def test_starter_has_no_capabilities() -> None:
    """Starter is Core-only: detection + recommendations stay ungated for it."""
    assert capabilities(PlanTier.STARTER) == frozenset()


def test_professional_has_exactly_eight_capabilities() -> None:
    assert len(capabilities(PlanTier.PROFESSIONAL)) == 8


def test_business_has_all_twelve_capabilities() -> None:
    assert len(capabilities(PlanTier.BUSINESS)) == 12
    assert {c.value for c in capabilities(PlanTier.BUSINESS)} == _APPENDIX_A_CAPABILITIES
