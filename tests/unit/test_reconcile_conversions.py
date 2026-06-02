from __future__ import annotations

from adcopilot.application.use_cases.reconcile_conversions import (
    ReconciliationVerdict,
    reconcile_conversions,
)


def test_no_data_when_both_zero() -> None:
    r = reconcile_conversions(ga4_conversions=0, ads_conversions=0)
    assert r.verdict is ReconciliationVerdict.NO_DATA


def test_aligned_within_threshold() -> None:
    r = reconcile_conversions(ga4_conversions=104, ads_conversions=100)
    assert r.verdict is ReconciliationVerdict.ALIGNED
    assert abs(r.discrepancy_pct) <= 15


def test_ads_higher_than_ga4() -> None:
    r = reconcile_conversions(ga4_conversions=50, ads_conversions=100)
    assert r.verdict is ReconciliationVerdict.ADS_HIGHER
    assert r.discrepancy_pct < 0


def test_ga4_higher_than_ads() -> None:
    r = reconcile_conversions(ga4_conversions=200, ads_conversions=100)
    assert r.verdict is ReconciliationVerdict.GA4_HIGHER
    assert r.discrepancy_pct > 15


def test_one_side_zero_is_a_discrepancy_not_no_data() -> None:
    r = reconcile_conversions(ga4_conversions=80, ads_conversions=0)
    assert r.verdict is ReconciliationVerdict.GA4_HIGHER
