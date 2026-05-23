"""Tests for RemoveRedundantMatchTypeExecutor."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from adcopilot.application.executors.remove_redundant_match_type import (
    RemoveRedundantMatchTypeExecutor,
)
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
        kind=RecommendationKind.MATCH_TYPE_REDUNDANCY,
        severity=RecommendationSeverity.MEDIUM,
        target=target,
        payload={},
        evidence=evidence,
        estimated_monthly_savings_micros=0,
        created_at=_NOW,
        status=RecommendationStatus.APPROVED,
    )


@pytest.mark.asyncio
async def test_pauses_broad_keyword_when_exact_exists() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        target={"ad_group_id": "50", "criterion_id": "77"},
        evidence={"keyword_text": "buty sportowe", "redundant_match_type": "BROAD", "kept_match_type": "EXACT"},
    )
    result = await RemoveRedundantMatchTypeExecutor().execute(rec, mutations, "token", "cid")

    assert len(mutations.calls) == 1
    call = mutations.calls[0]
    assert call["method"] == "pause_keyword"
    assert call["ad_group_id"] == 50
    assert call["criterion_id"] == 77
    assert result["action"] == "broad_keyword_paused"


@pytest.mark.asyncio
async def test_pauses_broad_when_phrase_exists() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        target={"ad_group_id": "50", "criterion_id": "88"},
        evidence={"keyword_text": "buty sportowe", "redundant_match_type": "BROAD", "kept_match_type": "PHRASE"},
    )
    await RemoveRedundantMatchTypeExecutor().execute(rec, mutations, "token", "cid")
    assert mutations.calls[0]["method"] == "pause_keyword"


def test_match_type_redundancy_removed_from_non_executable() -> None:
    from adcopilot.domain.recommendation import NON_EXECUTABLE_KINDS
    assert RecommendationKind.MATCH_TYPE_REDUNDANCY not in NON_EXECUTABLE_KINDS
