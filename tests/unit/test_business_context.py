from __future__ import annotations

from adcopilot.domain.business_economics import BusinessEconomics


def test_context_configured_by_goal_or_target() -> None:
    assert BusinessEconomics(account_id="a").is_context_configured() is False
    assert BusinessEconomics(account_id="a", primary_goal="LEADS").is_context_configured() is True
    assert BusinessEconomics(account_id="a", target_cpa=80.0).is_context_configured() is True
    assert BusinessEconomics(account_id="a", target_roas=4.0).is_context_configured() is True


def test_value_config_independent_of_context() -> None:
    # is_configured() (value) and is_context_configured() are separate signals.
    e = BusinessEconomics(account_id="a", default_lead_value=150.0)
    assert e.is_configured() is True
    assert e.is_context_configured() is False
    e2 = BusinessEconomics(account_id="a", primary_goal="SALES")
    assert e2.is_configured() is False
    assert e2.is_context_configured() is True


def test_terms_default_to_empty_lists() -> None:
    e = BusinessEconomics(account_id="a")
    assert e.brand_terms == []
    assert e.excluded_terms == []
