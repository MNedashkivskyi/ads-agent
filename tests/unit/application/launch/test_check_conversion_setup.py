"""Unit tests for conversion tracking check logic."""
from datetime import date

from adcopilot.application.use_cases.launch.check_conversion_setup import (
    has_macro_conversion_tracking,
)
from adcopilot.domain.entities import AccountId
from adcopilot.domain.snapshot import ConversionActionSnapshot, SnapshotId


def _make_ca(category: str, status: str = "ENABLED", include: bool = True) -> ConversionActionSnapshot:
    return ConversionActionSnapshot(
        id=SnapshotId("00000000-0000-0000-0000-000000000001"),
        account_id=AccountId("123"),
        snapshot_date=date.today(),
        conversion_action_id=1,
        name="test",
        category=category,
        counting_type="ONE_PER_CLICK",
        status=status,
        include_in_conversions_metric=include,
    )


def test_no_conversions_returns_false():
    assert has_macro_conversion_tracking([]) is False


def test_page_view_only_returns_false():
    assert has_macro_conversion_tracking([_make_ca("PAGE_VIEW")]) is False


def test_default_category_returns_false():
    assert has_macro_conversion_tracking([_make_ca("DEFAULT")]) is False


def test_purchase_returns_true():
    assert has_macro_conversion_tracking([_make_ca("PURCHASE")]) is True


def test_lead_returns_true():
    assert has_macro_conversion_tracking([_make_ca("LEAD")]) is True


def test_signup_returns_true():
    assert has_macro_conversion_tracking([_make_ca("SIGNUP")]) is True


def test_phone_call_returns_true():
    assert has_macro_conversion_tracking([_make_ca("PHONE_CALL")]) is True


def test_disabled_purchase_returns_false():
    assert has_macro_conversion_tracking([_make_ca("PURCHASE", status="HIDDEN")]) is False


def test_not_included_in_conversions_returns_false():
    assert has_macro_conversion_tracking([_make_ca("PURCHASE", include=False)]) is False


def test_mixed_returns_true_if_any_macro():
    actions = [_make_ca("PAGE_VIEW"), _make_ca("LEAD")]
    assert has_macro_conversion_tracking(actions) is True
