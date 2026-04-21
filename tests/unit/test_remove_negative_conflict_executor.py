"""Tests for RemoveNegativeConflictExecutor."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from adcopilot.application.executors.remove_negative_conflict import RemoveNegativeConflictExecutor
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
        kind=RecommendationKind.NEGATIVE_KEYWORD_CONFLICT,
        severity=RecommendationSeverity.HIGH,
        target=target,
        payload={},
        evidence=evidence,
        estimated_monthly_savings_micros=0,
        created_at=_NOW,
        status=RecommendationStatus.APPROVED,
    )


@pytest.mark.asyncio
async def test_campaign_level_removal() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        target={"criterion_id": "999", "campaign_id": "10"},
        evidence={"conflict_scope": "campaign", "negative_keyword_text": "free", "negative_match_type": "EXACT"},
    )
    result = await RemoveNegativeConflictExecutor().execute(rec, mutations, "token", "cid")

    assert len(mutations.calls) == 1
    call = mutations.calls[0]
    assert call["method"] == "remove_campaign_negative_keyword"
    assert call["campaign_id"] == 10
    assert call["keyword_text"] == "free"
    assert result["action"] == "negative_conflict_removed"


@pytest.mark.asyncio
async def test_ad_group_level_removal() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        target={"criterion_id": "999", "campaign_id": "10", "ad_group_id": "20"},
        evidence={"conflict_scope": "ad_group", "negative_keyword_text": "free", "negative_match_type": "BROAD"},
    )
    result = await RemoveNegativeConflictExecutor().execute(rec, mutations, "token", "cid")

    call = mutations.calls[0]
    assert call["method"] == "remove_ad_group_negative_keyword"
    assert call["ad_group_id"] == 20


def test_negative_keyword_conflict_removed_from_non_executable() -> None:
    from adcopilot.domain.recommendation import NON_EXECUTABLE_KINDS
    assert RecommendationKind.NEGATIVE_KEYWORD_CONFLICT not in NON_EXECUTABLE_KINDS
