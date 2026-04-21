"""Tests for PerformanceBaseline domain entity and baseline capture."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from adcopilot.domain.entities import AccountId
from adcopilot.domain.performance_tracking import PerformanceBaseline, PerformanceComparison
from adcopilot.domain.recommendation import RecommendationId


def _baseline(
    conversions: float = 10.0,
    cost_micros: int = 500_000_000,
    clicks: int = 200,
    impressions: int = 10_000,
) -> PerformanceBaseline:
    return PerformanceBaseline.create(
        recommendation_id=RecommendationId(str(uuid.uuid4())),
        account_id=AccountId("acct-1"),
        entity_type="campaign",
        entity_id=123,
        baseline_date=date(2026, 4, 1),
        cost_micros=cost_micros,
        clicks=clicks,
        impressions=impressions,
        conversions=conversions,
        conv_value=0.0,
        captured_at=datetime(2026, 4, 1, tzinfo=UTC),
    )


def test_baseline_computes_cpa() -> None:
    b = _baseline(conversions=10.0, cost_micros=500_000_000)
    assert b.cpa_micros == 50_000_000


def test_baseline_computes_ctr() -> None:
    b = _baseline(clicks=200, impressions=10_000)
    assert abs(b.ctr - 0.02) < 0.0001


def test_baseline_zero_conversions_cpa_is_zero() -> None:
    b = _baseline(conversions=0.0)
    assert b.cpa_micros == 0


def test_comparison_improved_verdict() -> None:
    b = _baseline(conversions=10.0, cost_micros=500_000_000)
    # CPA drops from 50M to 40M = -20% → IMPROVED
    comp = PerformanceComparison.create(
        recommendation_id=b.recommendation_id,
        baseline=b,
        comparison_window_days=7,
        current_cost_micros=400_000_000,
        current_clicks=200,
        current_impressions=10_000,
        current_conversions=10.0,
        compared_at=datetime(2026, 4, 8, tzinfo=UTC),
    )
    assert comp.verdict == "IMPROVED"
    assert comp.delta_cpa_pct < -5.0


def test_comparison_degraded_verdict() -> None:
    b = _baseline(conversions=10.0, cost_micros=500_000_000)
    # CPA rises from 50M to 70M = +40%, conversions drop → DEGRADED
    comp = PerformanceComparison.create(
        recommendation_id=b.recommendation_id,
        baseline=b,
        comparison_window_days=7,
        current_cost_micros=700_000_000,
        current_clicks=200,
        current_impressions=10_000,
        current_conversions=10.0,
        compared_at=datetime(2026, 4, 8, tzinfo=UTC),
    )
    # CPA = 700M/10 = 70M, up 40%, conversions same → neutral (not degraded since conversions didn't drop)
    # Let's use fewer conversions
    comp2 = PerformanceComparison.create(
        recommendation_id=b.recommendation_id,
        baseline=b,
        comparison_window_days=7,
        current_cost_micros=700_000_000,
        current_clicks=200,
        current_impressions=10_000,
        current_conversions=8.0,  # fewer conversions
        compared_at=datetime(2026, 4, 8, tzinfo=UTC),
    )
    assert comp2.verdict == "DEGRADED"


def test_comparison_neutral_verdict() -> None:
    b = _baseline(conversions=10.0, cost_micros=500_000_000)
    comp = PerformanceComparison.create(
        recommendation_id=b.recommendation_id,
        baseline=b,
        comparison_window_days=7,
        current_cost_micros=510_000_000,
        current_clicks=200,
        current_impressions=10_000,
        current_conversions=10.0,
        compared_at=datetime(2026, 4, 8, tzinfo=UTC),
    )
    assert comp.verdict == "NEUTRAL"
