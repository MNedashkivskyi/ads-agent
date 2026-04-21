"""Tests for CompareRecommendationPerformanceUseCase."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from adcopilot.application.use_cases.compare_recommendation_performance import (
    CompareRecommendationPerformanceUseCase,
)
from adcopilot.domain.entities import AccountId
from adcopilot.domain.performance_tracking import PerformanceBaseline
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_NOW = datetime(2026, 4, 15, 6, 0, tzinfo=UTC)  # 7 days after execution on April 8


def _make_rec() -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=AccountId("acct-1"),
        kind=RecommendationKind.DEVICE_BID_ADJUSTMENT,
        severity=RecommendationSeverity.HIGH,
        target={"campaign_id": "100"},
        payload={},
        evidence={},
        estimated_monthly_savings_micros=0,
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
        status=RecommendationStatus.EXECUTED,
    )


def _make_baseline(rec: Recommendation) -> PerformanceBaseline:
    return PerformanceBaseline.create(
        recommendation_id=rec.id,
        account_id=rec.account_id,
        entity_type="campaign",
        entity_id=100,
        baseline_date=date(2026, 4, 8),
        cost_micros=500_000_000,
        clicks=200,
        impressions=10_000,
        conversions=10.0,
        conv_value=0.0,
        captured_at=datetime(2026, 4, 8, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_creates_comparison_for_7_and_14_days() -> None:
    rec = _make_rec()
    baseline = _make_baseline(rec)

    rec_repo = AsyncMock()
    rec_repo.list_executed_in_date_range.return_value = [rec]

    baseline_repo = AsyncMock()
    baseline_repo.get_by_recommendation.return_value = baseline

    comparison_repo = AsyncMock()
    comparison_repo.exists.return_value = False
    comparison_repo.save = AsyncMock()

    async def _fetcher(account_id, entity_type, entity_id):
        return {"cost_micros": 400_000_000, "clicks": 200, "impressions": 10_000, "conversions": 10.0}

    use_case = CompareRecommendationPerformanceUseCase(
        rec_repo=rec_repo,
        baseline_repo=baseline_repo,
        comparison_repo=comparison_repo,
        snapshot_fetcher=_fetcher,
    )
    result = await use_case.run(now=_NOW)

    # Called once per window (7 and 14 days) × 1 rec = 2 comparisons
    assert comparison_repo.save.call_count == 2
    assert result["comparisons_created"] == 2


@pytest.mark.asyncio
async def test_skips_existing_comparisons() -> None:
    rec = _make_rec()
    baseline = _make_baseline(rec)

    rec_repo = AsyncMock()
    rec_repo.list_executed_in_date_range.return_value = [rec]

    baseline_repo = AsyncMock()
    baseline_repo.get_by_recommendation.return_value = baseline

    comparison_repo = AsyncMock()
    comparison_repo.exists.return_value = True  # already compared

    use_case = CompareRecommendationPerformanceUseCase(
        rec_repo=rec_repo,
        baseline_repo=baseline_repo,
        comparison_repo=comparison_repo,
        snapshot_fetcher=AsyncMock(return_value={}),
    )
    result = await use_case.run(now=_NOW)
    assert result["comparisons_created"] == 0
    assert result["comparisons_skipped"] == 2


@pytest.mark.asyncio
async def test_skips_when_no_baseline() -> None:
    rec = _make_rec()

    rec_repo = AsyncMock()
    rec_repo.list_executed_in_date_range.return_value = [rec]

    baseline_repo = AsyncMock()
    baseline_repo.get_by_recommendation.return_value = None

    comparison_repo = AsyncMock()
    comparison_repo.exists.return_value = False

    use_case = CompareRecommendationPerformanceUseCase(
        rec_repo=rec_repo,
        baseline_repo=baseline_repo,
        comparison_repo=comparison_repo,
        snapshot_fetcher=AsyncMock(),
    )
    result = await use_case.run(now=_NOW)
    assert result["comparisons_created"] == 0
    assert result["comparisons_skipped"] == 2
