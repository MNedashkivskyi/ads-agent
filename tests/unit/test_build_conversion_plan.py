"""Unit tests for the per-action conversion plan builder."""

from __future__ import annotations

from adcopilot.application.use_cases.build_conversion_plan import build_conversion_plan
from adcopilot.domain.business_economics import BusinessEconomics
from adcopilot.domain.conversion_tracking.setup import ConversionActionTagInfo
from adcopilot.domain.conversion_tracking.trigger_rules import TriggerKind


def _action(name: str, category: str, suffix: str = "1") -> ConversionActionTagInfo:
    return ConversionActionTagInfo(
        conversion_action_id=int(suffix),
        name=name,
        category=category,
        conversion_id=f"AW-70930905{suffix}",
        conversion_label=f"label_{suffix}",
    )


def test_one_plan_item_per_action_with_real_ids() -> None:
    actions = [_action("Zakup", "PURCHASE", "1"), _action("Telefon", "PHONE_CALL_LEAD", "2")]
    plan = build_conversion_plan(actions, "woocommerce", [])
    assert [p.conversion_action_id for p in plan] == [1, 2]
    assert plan[0].conversion_id == "AW-709309051"
    assert plan[0].trigger_kind is TriggerKind.PAGE_URL_CONTAINS
    assert plan[0].trigger_hint == "order-received"
    assert plan[1].trigger_kind is TriggerKind.TEL_CLICK


def test_purchase_value_from_economics() -> None:
    econ = BusinessEconomics(
        account_id="acc", avg_order_value=200.0, profit_margin_pct=25.0, currency_code="PLN"
    )
    plan = build_conversion_plan([_action("Zakup", "PURCHASE")], "woocommerce", [], econ)
    assert plan[0].value == 50.0  # 200 * 25%
    assert plan[0].currency == "PLN"


def test_lead_value_from_economics() -> None:
    econ = BusinessEconomics(account_id="acc", default_lead_value=80.0, currency_code="EUR")
    plan = build_conversion_plan([_action("Formularz", "LEAD")], "wordpress", [], econ)
    assert plan[0].value == 80.0
    assert plan[0].currency == "EUR"


def test_no_economics_means_no_value() -> None:
    plan = build_conversion_plan([_action("Zakup", "PURCHASE")], "woocommerce", [], None)
    assert plan[0].value is None
    assert plan[0].currency is None
