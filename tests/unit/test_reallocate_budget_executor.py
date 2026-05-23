"""Tests for ReallocateBudgetExecutor."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from adcopilot.application.executors.reallocate_budget import ReallocateBudgetExecutor
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
        kind=RecommendationKind.REALLOCATE_BUDGET,
        severity=RecommendationSeverity.HIGH,
        target=target,
        payload={},
        evidence=evidence,
        estimated_monthly_savings_micros=0,
        created_at=_NOW,
        status=RecommendationStatus.APPROVED,
    )


@pytest.mark.asyncio
async def test_reallocates_20_percent() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        target={"from_campaign_id": "10", "to_campaign_id": "20"},
        evidence={"donor_budget_micros": 10_000_000, "receiver_budget_micros": 5_000_000},
    )
    result = await ReallocateBudgetExecutor().execute(rec, mutations, "token", "cid")

    assert len(mutations.calls) == 2
    donor_call = next(c for c in mutations.calls if c["campaign_id"] == 10)
    receiver_call = next(c for c in mutations.calls if c["campaign_id"] == 20)
    assert donor_call["new_budget_micros"] == 8_000_000
    assert receiver_call["new_budget_micros"] == 7_000_000
    assert result["transfer_micros"] == 2_000_000
    assert result["action"] == "budget_reallocated"


@pytest.mark.asyncio
async def test_donor_too_low_raises() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        target={"from_campaign_id": "10", "to_campaign_id": "20"},
        evidence={"donor_budget_micros": 1_000_000, "receiver_budget_micros": 5_000_000},
    )
    with pytest.raises(ValueError, match="too low"):
        await ReallocateBudgetExecutor().execute(rec, mutations, "token", "cid")


def test_reallocate_budget_removed_from_non_executable() -> None:
    from adcopilot.domain.recommendation import NON_EXECUTABLE_KINDS

    assert RecommendationKind.REALLOCATE_BUDGET not in NON_EXECUTABLE_KINDS
