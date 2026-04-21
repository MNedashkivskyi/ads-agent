"""Tests for DeviceBidAdjustmentExecutor."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from adcopilot.application.executors.device_bid_adjustment import DeviceBidAdjustmentExecutor
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


def _rec(target: dict, evidence: dict) -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=AccountId("acct-1"),
        kind=RecommendationKind.DEVICE_BID_ADJUSTMENT,
        severity=RecommendationSeverity.HIGH,
        target=target,
        payload={},
        evidence=evidence,
        estimated_monthly_savings_micros=0,
        created_at=_NOW,
        status=RecommendationStatus.APPROVED,
    )


@pytest.mark.asyncio
async def test_executor_calls_set_device_bid_modifier() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        target={"campaign_id": "123"},
        evidence={"mobile_cpa_micros": 200_000_000, "desktop_cpa_micros": 100_000_000},
    )
    result = await DeviceBidAdjustmentExecutor().execute(rec, mutations, "token", "cid")

    assert len(mutations.calls) == 1
    call = mutations.calls[0]
    assert call["method"] == "set_device_bid_modifier"
    assert call["campaign_id"] == 123
    # modifier = -(1 - 100/200) = -0.5
    assert abs(call["bid_modifier"] - (-0.5)) < 0.001
    assert result["action"] == "device_bid_modifier_set"


@pytest.mark.asyncio
async def test_bid_modifier_clamped_lower_bound() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        target={"campaign_id": "1"},
        evidence={"mobile_cpa_micros": 1_000_000_000, "desktop_cpa_micros": 10_000_000},
    )
    await DeviceBidAdjustmentExecutor().execute(rec, mutations, "token", "cid")
    assert mutations.calls[0]["bid_modifier"] >= -0.90


@pytest.mark.asyncio
async def test_bid_modifier_clamped_upper_bound() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        target={"campaign_id": "1"},
        evidence={"mobile_cpa_micros": 101_000_000, "desktop_cpa_micros": 100_000_000},
    )
    await DeviceBidAdjustmentExecutor().execute(rec, mutations, "token", "cid")
    assert mutations.calls[0]["bid_modifier"] <= -0.20


def test_device_bid_adjustment_removed_from_non_executable() -> None:
    from adcopilot.domain.recommendation import NON_EXECUTABLE_KINDS
    assert RecommendationKind.DEVICE_BID_ADJUSTMENT not in NON_EXECUTABLE_KINDS
