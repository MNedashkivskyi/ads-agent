from __future__ import annotations

from adcopilot.domain.business_economics import BusinessEconomics
from adcopilot.domain.value_derivation import derive_conversion_value


def test_lead_uses_default_lead_value() -> None:
    econ = BusinessEconomics(account_id="a", default_lead_value=120.0)
    assert derive_conversion_value(econ, category="SUBMIT_LEAD_FORM") == 120.0


def test_ecommerce_uses_aov_times_margin() -> None:
    econ = BusinessEconomics(account_id="a", avg_order_value=200.0, profit_margin_pct=30.0)
    # 200 * 0.30 = 60 profit-based value
    assert derive_conversion_value(econ, category="PURCHASE") == 60.0


def test_ecommerce_without_margin_uses_aov() -> None:
    econ = BusinessEconomics(account_id="a", avg_order_value=200.0)
    assert derive_conversion_value(econ, category="PURCHASE") == 200.0


def test_lead_falls_back_to_ltv_when_no_default() -> None:
    econ = BusinessEconomics(account_id="a", customer_ltv=900.0)
    assert derive_conversion_value(econ, category="PHONE_CALL_LEAD") == 900.0


def test_returns_none_when_nothing_configured() -> None:
    econ = BusinessEconomics(account_id="a")
    assert derive_conversion_value(econ, category="PURCHASE") is None
