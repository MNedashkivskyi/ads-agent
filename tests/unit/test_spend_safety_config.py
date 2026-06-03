from __future__ import annotations

import pytest

from adcopilot.domain.spend_safety import SpendSafetyConfig, SpendSafetyConfigError


def test_defaults_not_configured() -> None:
    c = SpendSafetyConfig(account_id="acc-1")
    assert c.is_configured() is False
    assert c.auto_pause_enabled is False
    assert c.max_budget_increase_pct == 50.0


def test_is_configured_when_any_cap_set() -> None:
    assert SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=1).is_configured()
    assert SpendSafetyConfig(account_id="a", daily_spend_cap_micros=1).is_configured()
    assert SpendSafetyConfig(account_id="a", per_campaign_daily_cap_micros=1).is_configured()


def test_negative_cap_rejected() -> None:
    with pytest.raises(SpendSafetyConfigError):
        SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=-1)


def test_pct_bounds_enforced() -> None:
    with pytest.raises(SpendSafetyConfigError):
        SpendSafetyConfig(account_id="a", max_budget_increase_pct=0)
    with pytest.raises(SpendSafetyConfigError):
        SpendSafetyConfig(account_id="a", warning_threshold_pct=101)
