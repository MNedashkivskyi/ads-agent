"""Unit tests for cross-account report aggregation (Phase 3 / T3.3)."""

from __future__ import annotations

from adcopilot.application.use_cases.aggregate_cross_account_report import (
    ReportBranding,
    aggregate_metrics,
    build_cross_account_report,
)


def test_aggregate_sums_additive_metrics() -> None:
    out = aggregate_metrics(
        [
            {"spend_pln": 100.0, "clicks": 50, "impressions": 1000, "conversions": 5},
            {"spend_pln": 50.0, "clicks": 25, "impressions": 500, "conversions": 5},
        ]
    )
    assert out["spend_pln"] == 150.0
    assert out["clicks"] == 75
    assert out["impressions"] == 1500
    assert out["conversions"] == 10
    assert out["account_count"] == 2
    # cpa = 150 / 10 = 15.0
    assert out["cpa"] == 15.0
    # ctr = 75 / 1500 * 100 = 5.0
    assert out["ctr"] == 5.0


def test_aggregate_handles_zero_conversions_and_impressions() -> None:
    out = aggregate_metrics([{"spend_pln": 10.0, "clicks": 0, "impressions": 0, "conversions": 0}])
    assert out["cpa"] is None
    assert out["ctr"] is None


def test_aggregate_handles_missing_keys() -> None:
    out = aggregate_metrics([{}, {"spend_pln": 5.0}])
    assert out["spend_pln"] == 5.0
    assert out["clicks"] == 0


def test_build_report_includes_branding_and_accounts() -> None:
    per_account = [
        {"account_id": "a", "metrics": {"spend_pln": 100.0, "conversions": 4}, "summary_pl": "ok"},
        {"account_id": "b", "metrics": {"spend_pln": 100.0, "conversions": 4}, "summary_pl": "ok"},
    ]
    report = build_cross_account_report(
        per_account,
        ReportBranding(company_name="Agencja X", logo_url="https://x/logo.png"),
        period_start="2026-05-01",
        period_end="2026-05-31",
    )
    assert report["branding"]["company_name"] == "Agencja X"
    assert report["branding"]["logo_url"] == "https://x/logo.png"
    assert report["totals"]["spend_pln"] == 200.0
    assert report["totals"]["account_count"] == 2
    assert len(report["accounts"]) == 2
