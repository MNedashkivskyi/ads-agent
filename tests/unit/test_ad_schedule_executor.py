"""Tests for AdScheduleAdjustmentExecutor."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from adcopilot.application.executors.ad_schedule_adjustment import AdScheduleAdjustmentExecutor
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)
from adcopilot.infrastructure.google_ads.fake_mutations import FakeGoogleAdsMutations

_NOW = datetime(2026, 4, 10, tzinfo=UTC)


def _rec(target: dict) -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=AccountId("acct-1"),
        kind=RecommendationKind.AD_SCHEDULE_ADJUSTMENT,
        severity=RecommendationSeverity.HIGH,
        target=target,
        payload={},
        evidence={},
        estimated_monthly_savings_micros=0,
        created_at=_NOW,
        status=RecommendationStatus.APPROVED,
    )


@pytest.mark.asyncio
async def test_executor_sets_schedule_with_minus_one() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec({"campaign_id": "200", "hour_of_day": "14"})
    result = await AdScheduleAdjustmentExecutor().execute(rec, mutations, "token", "cid")

    assert len(mutations.calls) == 1
    call = mutations.calls[0]
    assert call["method"] == "set_ad_schedule_bid_modifier"
    assert call["campaign_id"] == 200
    assert call["hour_of_day"] == 14
    assert call["bid_modifier"] == -1.0
    assert result["action"] == "ad_schedule_bid_modifier_set"


@pytest.mark.asyncio
async def test_executor_handles_hour_zero() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec({"campaign_id": "1", "hour_of_day": "0"})
    result = await AdScheduleAdjustmentExecutor().execute(rec, mutations, "token", "cid")
    assert mutations.calls[0]["hour_of_day"] == 0


@pytest.mark.asyncio
async def test_executor_handles_hour_23() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec({"campaign_id": "1", "hour_of_day": "23"})
    result = await AdScheduleAdjustmentExecutor().execute(rec, mutations, "token", "cid")
    assert mutations.calls[0]["hour_of_day"] == 23


def test_ad_schedule_removed_from_non_executable() -> None:
    from adcopilot.domain.recommendation import NON_EXECUTABLE_KINDS
    assert RecommendationKind.AD_SCHEDULE_ADJUSTMENT not in NON_EXECUTABLE_KINDS
