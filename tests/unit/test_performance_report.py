"""Tests for performance report formatter and SendPerformanceReportUseCase."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from adcopilot.domain.entities import AccountId
from adcopilot.domain.performance_tracking import PerformanceBaseline, PerformanceComparison
from adcopilot.domain.recommendation import RecommendationId
from adcopilot.infrastructure.telegram.performance_report import format_weekly_report


def _make_comparison(verdict: str, delta_cpa_pct: float = -20.0) -> PerformanceComparison:
    rec_id = RecommendationId(str(uuid.uuid4()))
    baseline = PerformanceBaseline.create(
        recommendation_id=rec_id,
        account_id=AccountId("acct-1"),
        entity_type="campaign",
        entity_id=1,
        baseline_date=date(2026, 4, 1),
        cost_micros=500_000_000,
        clicks=100,
        impressions=5_000,
        conversions=10.0,
        conv_value=0.0,
        captured_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    return PerformanceComparison.create(
        recommendation_id=rec_id,
        baseline=baseline,
        comparison_window_days=7,
        current_cost_micros=400_000_000 if verdict == "IMPROVED" else 600_000_000,
        current_clicks=100,
        current_impressions=5_000,
        current_conversions=10.0 if verdict != "DEGRADED" else 8.0,
        compared_at=datetime(2026, 4, 8, tzinfo=UTC),
    )


def test_format_report_groups_by_verdict() -> None:
    improved = _make_comparison("IMPROVED")
    comparisons = [(improved, "Dostosowanie stawek")]

    report = format_weekly_report("Moje konto", comparisons, cumulative_savings_micros=1_240_000_000)
    assert "Podsumowanie tygodnia" in report
    assert "✅" in report
    assert "oszczędności" in report


def test_format_report_empty_returns_empty() -> None:
    assert format_weekly_report("konto", []) == ""


def test_format_report_shows_degraded_emoji() -> None:
    degraded = _make_comparison("DEGRADED")
    report = format_weekly_report("konto", [(degraded, "Pauza słowa")], 0)
    assert "❌" in report


def test_format_report_improved_shows_cpa_delta() -> None:
    improved = _make_comparison("IMPROVED")
    report = format_weekly_report("konto", [(improved, "Stawka mobilna")], 0)
    assert "CPA" in report
    assert "%" in report
