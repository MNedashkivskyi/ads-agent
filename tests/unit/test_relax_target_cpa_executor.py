"""Tests for RelaxTargetCpaExecutor."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from adcopilot.application.executors.relax_target_cpa import RelaxTargetCpaExecutor
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
        kind=RecommendationKind.RELAX_TARGET_CPA,
        severity=RecommendationSeverity.HIGH,
        target=target,
        payload={},
        evidence=evidence,
        estimated_monthly_savings_micros=0,
        created_at=_NOW,
        status=RecommendationStatus.APPROVED,
    )


@pytest.mark.asyncio
async def test_executor_sets_suggested_target_cpa() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        target={"campaign_id": "300"},
        evidence={
            "suggested_target_cpa_micros": 75_000_000,
            "current_target_cpa_micros": 50_000_000,
        },
    )
    result = await RelaxTargetCpaExecutor().execute(rec, mutations, "token", "cid")

    assert len(mutations.calls) == 1
    call = mutations.calls[0]
    assert call["method"] == "set_target_cpa"
    assert call["campaign_id"] == 300
    assert call["target_cpa_micros"] == 75_000_000
    assert result["action"] == "target_cpa_updated"
    assert result["original_target_cpa_micros"] == 50_000_000


def test_relax_target_cpa_removed_from_non_executable() -> None:
    from adcopilot.domain.recommendation import NON_EXECUTABLE_KINDS

    assert RecommendationKind.RELAX_TARGET_CPA not in NON_EXECUTABLE_KINDS
