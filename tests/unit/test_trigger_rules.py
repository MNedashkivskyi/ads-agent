"""Unit tests for the conversion category → GTM trigger taxonomy."""

from __future__ import annotations

import pytest

from adcopilot.domain.conversion_tracking.trigger_rules import (
    TriggerKind,
    strategy_for_category,
)


@pytest.mark.parametrize(
    ("category", "expected_kind"),
    [
        ("PHONE_CALL_LEAD", TriggerKind.TEL_CLICK),
        ("DOWNLOAD", TriggerKind.FILE_DOWNLOAD_CLICK),
        ("LEAD", TriggerKind.FORM_SUBMISSION),
        ("SUBMIT_LEAD_FORM", TriggerKind.FORM_SUBMISSION),
        ("PURCHASE", TriggerKind.PAGE_URL_CONTAINS),
        ("SIGNUP", TriggerKind.PAGE_URL_CONTAINS),
        ("PAGE_VIEW", TriggerKind.PAGE_URL_CONTAINS),
        ("DEFAULT", TriggerKind.PAGE_URL_CONTAINS),
        ("SOMETHING_NEW", TriggerKind.PAGE_URL_CONTAINS),
    ],
)
def test_category_maps_to_expected_trigger(category: str, expected_kind: TriggerKind) -> None:
    assert strategy_for_category(category, "custom", []).kind is expected_kind


def test_phone_and_download_need_no_user_input() -> None:
    assert strategy_for_category("PHONE_CALL_LEAD", "custom", []).needs_user_input is False
    assert strategy_for_category("DOWNLOAD", "custom", []).needs_user_input is False
    assert strategy_for_category("LEAD", "custom", []).needs_user_input is False


def test_purchase_uses_platform_default_path() -> None:
    woo = strategy_for_category("PURCHASE", "woocommerce", [])
    assert woo.default_hint == "order-received"
    assert woo.needs_user_input is False

    shopify = strategy_for_category("PURCHASE", "shopify", [])
    assert shopify.default_hint == "thank_you"
    assert shopify.needs_user_input is False


def test_purchase_on_custom_platform_falls_back_to_url_scan() -> None:
    urls = ["https://shop.example.com/cart/dziekujemy?order=1"]
    strat = strategy_for_category("PURCHASE", "custom", urls)
    assert strat.default_hint == "dziekujemy"
    assert strat.needs_user_input is False


def test_signup_without_known_success_url_asks_user() -> None:
    strat = strategy_for_category("SIGNUP", "custom", ["https://app.example.com/pricing"])
    assert strat.kind is TriggerKind.PAGE_URL_CONTAINS
    assert strat.default_hint == ""
    assert strat.needs_user_input is True


def test_signup_with_obvious_success_path_is_prefilled() -> None:
    strat = strategy_for_category("SIGNUP", "custom", ["https://app.example.com/thank-you"])
    assert strat.default_hint == "thank-you"
    assert strat.needs_user_input is False
