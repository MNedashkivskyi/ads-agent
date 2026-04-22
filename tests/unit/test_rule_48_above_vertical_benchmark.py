"""Tests for Rule 48 — CPA Above Vertical Benchmark."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from adcopilot.application.detection.base import DetectionContext, HistoricalStats
from adcopilot.application.detection.rules.rule_48_above_vertical_benchmark import (
    AboveVerticalBenchmarkRule,
    _P75_MULTIPLIER,
)
from adcopilot.domain.benchmarking import AccountMetrics, VerticalBenchmarkSnapshot, BenchmarkId
from adcopilot.domain.entities import AccountId, GoogleAdsAccount, UserId
from adcopilot.domain.recommendation import RecommendationKind


_WEEK = date(2026, 4, 20)
_NOW = datetime(2026, 4, 22, tzinfo=UTC)


def _account() -> GoogleAdsAccount:
    return GoogleAdsAccount(
        id=AccountId("acc-1"),
        user_id=UserId("u1"),
        customer_id="acc-1",
        descriptive_name="Test",
        currency="PLN",
        timezone="Europe/Warsaw",
        is_manager=False,
        write_enabled=True,
        connected_at=_NOW,
    )


def _history(avg_cpa_micros: int) -> HistoricalStats:
    return HistoricalStats(
        avg_cpa_micros=avg_cpa_micros,
        total_cost_micros=50_000_000,
        total_conversions=10.0,
    )


def _benchmark(p75_cpa_micros: int, median_cpa_micros: int = 2_000_000) -> VerticalBenchmarkSnapshot:
    return VerticalBenchmarkSnapshot(
        id=BenchmarkId(str(uuid4())),
        vertical="salon",
        city_tier=1,
        snapshot_week=_WEEK,
        account_count=8,
        avg_cpa_micros=2_200_000,
        median_cpa_micros=median_cpa_micros,
        p25_cpa_micros=1_500_000,
        p75_cpa_micros=p75_cpa_micros,
        avg_ctr=0.05,
        avg_conversion_rate=0.03,
        avg_monthly_spend_micros=10_000_000,
        created_at=_NOW,
    )


def _ctx(
    avg_cpa_micros: int,
    benchmark: VerticalBenchmarkSnapshot | None,
) -> DetectionContext:
    return DetectionContext(
        account=_account(),
        campaigns=[],
        ad_groups=[],
        keywords=[],
        search_terms=[],
        ads=[],
        history=_history(avg_cpa_micros),
        snapshot_date=_WEEK,
        vertical_benchmark=benchmark,
    )


def test_no_benchmark_returns_empty() -> None:
    rule = AboveVerticalBenchmarkRule()
    result = rule.detect(_ctx(avg_cpa_micros=9_000_000, benchmark=None))
    assert result == []


def test_zero_account_cpa_returns_empty() -> None:
    rule = AboveVerticalBenchmarkRule()
    result = rule.detect(_ctx(avg_cpa_micros=0, benchmark=_benchmark(p75_cpa_micros=2_000_000)))
    assert result == []


def test_zero_p75_returns_empty() -> None:
    rule = AboveVerticalBenchmarkRule()
    result = rule.detect(_ctx(avg_cpa_micros=5_000_000, benchmark=_benchmark(p75_cpa_micros=0)))
    assert result == []


def test_cpa_below_threshold_no_recommendation() -> None:
    """account CPA = p75 * 1.4 — below the 1.5x threshold."""
    p75 = 2_000_000
    account_cpa = int(p75 * 1.4)
    rule = AboveVerticalBenchmarkRule()
    result = rule.detect(_ctx(avg_cpa_micros=account_cpa, benchmark=_benchmark(p75_cpa_micros=p75)))
    assert result == []


def test_cpa_exactly_at_threshold_no_recommendation() -> None:
    """account CPA = p75 * 1.5 — at threshold, not above."""
    p75 = 2_000_000
    account_cpa = int(p75 * _P75_MULTIPLIER)
    rule = AboveVerticalBenchmarkRule()
    result = rule.detect(_ctx(avg_cpa_micros=account_cpa, benchmark=_benchmark(p75_cpa_micros=p75)))
    assert result == []


def test_cpa_above_threshold_fires() -> None:
    """account CPA = p75 * 2.0 — well above 1.5x threshold."""
    p75 = 2_000_000
    account_cpa = p75 * 2
    rule = AboveVerticalBenchmarkRule()
    result = rule.detect(_ctx(avg_cpa_micros=account_cpa, benchmark=_benchmark(p75_cpa_micros=p75)))
    assert len(result) == 1
    rec = result[0]
    assert rec.kind == RecommendationKind.ABOVE_VERTICAL_BENCHMARK


def test_recommendation_payload_fields() -> None:
    p75 = 2_000_000
    account_cpa = 4_000_000  # 2x p75
    bench = _benchmark(p75_cpa_micros=p75, median_cpa_micros=1_800_000)
    rule = AboveVerticalBenchmarkRule()
    rec = rule.detect(_ctx(avg_cpa_micros=account_cpa, benchmark=bench))[0]

    payload = rec.payload
    assert payload["vertical"] == "salon"
    assert payload["city_tier"] == 1
    assert payload["benchmark_account_count"] == 8
    assert payload["account_cpa_pln"] == pytest.approx(4.0)
    assert payload["benchmark_p75_pln"] == pytest.approx(2.0)
    assert payload["pct_above_p75"] == pytest.approx(100.0)


def test_recommendation_account_id() -> None:
    p75 = 1_000_000
    account_cpa = 2_000_000
    rule = AboveVerticalBenchmarkRule()
    rec = rule.detect(_ctx(avg_cpa_micros=account_cpa, benchmark=_benchmark(p75_cpa_micros=p75)))[0]
    assert rec.account_id == "acc-1"  # customer_id used as account_id in payload
