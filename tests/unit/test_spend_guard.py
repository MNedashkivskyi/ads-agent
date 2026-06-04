from __future__ import annotations

from adcopilot.domain.spend_guard import (
    AccountSpendContext,
    SpendAction,
    evaluate_spend_action,
)
from adcopilot.domain.spend_safety import SpendSafetyConfig


def _ctx(**kw) -> AccountSpendContext:
    base = dict(month_to_date_spend_micros=0, today_spend_micros=0, days_elapsed=15, days_in_month=30)
    base.update(kw)
    return AccountSpendContext(**base)


def test_inert_when_not_configured() -> None:
    cfg = SpendSafetyConfig(account_id="a")  # no caps
    action = SpendAction(kind="INCREASE_BUDGET", current_budget_micros=1_000_000, new_budget_micros=100_000_000)
    assert evaluate_spend_action(action, cfg, _ctx()).allowed is True


def test_max_budget_increase_denied() -> None:
    cfg = SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=10_000_000_000, max_budget_increase_pct=50.0)
    action = SpendAction(kind="INCREASE_BUDGET", current_budget_micros=1_000_000, new_budget_micros=2_000_000)  # +100%
    d = evaluate_spend_action(action, cfg, _ctx())
    assert d.allowed is False
    assert d.code == "MAX_BUDGET_INCREASE"


def test_within_max_budget_increase_allowed() -> None:
    cfg = SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=10_000_000_000, max_budget_increase_pct=50.0)
    action = SpendAction(kind="INCREASE_BUDGET", current_budget_micros=1_000_000, new_budget_micros=1_200_000)  # +20%
    assert evaluate_spend_action(action, cfg, _ctx()).allowed is True


def test_per_campaign_daily_cap_denied() -> None:
    cfg = SpendSafetyConfig(account_id="a", per_campaign_daily_cap_micros=50_000_000)
    action = SpendAction(kind="ADJUST_BUDGET", current_budget_micros=40_000_000, new_budget_micros=60_000_000)
    d = evaluate_spend_action(action, cfg, _ctx())
    assert d.allowed is False
    assert d.code == "CAMPAIGN_DAILY_CAP"


def test_account_daily_cap_denied() -> None:
    cfg = SpendSafetyConfig(account_id="a", daily_spend_cap_micros=100_000_000, max_budget_increase_pct=1000)
    # today already spent 90 PLN, raising budget by +20 PLN -> 110 > 100 daily cap
    action = SpendAction(kind="INCREASE_BUDGET", current_budget_micros=10_000_000, new_budget_micros=30_000_000)
    d = evaluate_spend_action(action, cfg, _ctx(today_spend_micros=90_000_000))
    assert d.allowed is False
    assert d.code == "DAILY_CAP"


def test_monthly_cap_projection_denied() -> None:
    cfg = SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=1_000_000_000, max_budget_increase_pct=1000)
    # MTD 800 PLN at day 15/30 -> run-rate projects ~1600 PLN already over 1000 cap
    action = SpendAction(kind="INCREASE_BUDGET", current_budget_micros=10_000_000, new_budget_micros=12_000_000)
    d = evaluate_spend_action(action, cfg, _ctx(month_to_date_spend_micros=800_000_000, days_elapsed=15))
    assert d.allowed is False
    assert d.code == "MONTHLY_CAP"


def test_monthly_cap_within_pace_allowed() -> None:
    cfg = SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=10_000_000_000, max_budget_increase_pct=1000)
    action = SpendAction(kind="INCREASE_BUDGET", current_budget_micros=10_000_000, new_budget_micros=11_000_000)
    d = evaluate_spend_action(action, cfg, _ctx(month_to_date_spend_micros=100_000_000, days_elapsed=15))
    assert d.allowed is True


def test_budget_reduction_always_allowed() -> None:
    cfg = SpendSafetyConfig(account_id="a", daily_spend_cap_micros=1, monthly_spend_cap_micros=1)
    action = SpendAction(kind="ADJUST_BUDGET", current_budget_micros=50_000_000, new_budget_micros=20_000_000)
    assert evaluate_spend_action(action, cfg, _ctx()).allowed is True


def test_tcpa_relaxation_denied() -> None:
    cfg = SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=10_000_000_000, max_budget_increase_pct=50.0)
    action = SpendAction(
        kind="RELAX_TARGET_CPA", current_target_cpa_micros=40_000_000, new_target_cpa_micros=80_000_000
    )  # +100%
    d = evaluate_spend_action(action, cfg, _ctx())
    assert d.allowed is False
    assert d.code == "TCPA_RELAX"


def test_tcpa_tightening_allowed() -> None:
    cfg = SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=10_000_000_000)
    action = SpendAction(
        kind="RELAX_TARGET_CPA", current_target_cpa_micros=80_000_000, new_target_cpa_micros=60_000_000
    )
    assert evaluate_spend_action(action, cfg, _ctx()).allowed is True


def test_reallocation_out_of_scope_allowed() -> None:
    cfg = SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=1, daily_spend_cap_micros=1)
    action = SpendAction(kind="REALLOCATE_BUDGET", new_budget_micros=999_000_000)
    assert evaluate_spend_action(action, cfg, _ctx()).allowed is True
