"""Tests for PromoteSearchTermExecutor."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from adcopilot.application.executors.promote_search_term import PromoteSearchTermExecutor
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)
from adcopilot.infrastructure.google_ads.fake_mutations import FakeGoogleAdsMutations

_NOW = datetime(2026, 4, 22, tzinfo=UTC)


def _rec(search_term: str = "fryzjer warszawa", ad_group_id: int = 1001) -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=AccountId("acct-1"),
        kind=RecommendationKind.PROMOTE_SEARCH_TERM,
        severity=RecommendationSeverity.MEDIUM,
        target={"ad_group_id": ad_group_id, "search_term": search_term},
        payload={
            "search_term": search_term,
            "suggested_match_type": "EXACT",
            "suggested_ad_group_id": ad_group_id,
            "conversions": 5.0,
            "cpa_micros": 3_000_000,
        },
        evidence={},
        estimated_monthly_savings_micros=0,
        created_at=_NOW,
        status=RecommendationStatus.EXECUTED,
    )


@pytest.mark.asyncio
async def test_executor_calls_add_keyword() -> None:
    fake = FakeGoogleAdsMutations()
    executor = PromoteSearchTermExecutor()
    rec = _rec()
    await executor.execute(rec, fake, "tok", "cid-123")
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["method"] == "add_keyword"
    assert call["keyword_text"] == "fryzjer warszawa"
    assert call["match_type"] == "EXACT"
    assert call["ad_group_id"] == 1001


@pytest.mark.asyncio
async def test_executor_returns_audit_data() -> None:
    fake = FakeGoogleAdsMutations()
    executor = PromoteSearchTermExecutor()
    result = await executor.execute(_rec(), fake, "tok", "cid-123")
    assert result["search_term"] == "fryzjer warszawa"
    assert result["match_type"] == "EXACT"
    assert result["criterion_id"] == 99999  # fake criterion_id


@pytest.mark.asyncio
async def test_executor_uses_payload_ad_group_id() -> None:
    fake = FakeGoogleAdsMutations()
    executor = PromoteSearchTermExecutor()
    rec = _rec(ad_group_id=5555)
    await executor.execute(rec, fake, "tok", "cid-123")
    assert fake.calls[0]["ad_group_id"] == 5555


@pytest.mark.asyncio
async def test_undo_pauses_promoted_keyword() -> None:
    """Undo logic: pause_ad_group_keyword_by_text is available in fake mutations."""
    fake = FakeGoogleAdsMutations()
    await fake.pause_ad_group_keyword_by_text(
        refresh_token="tok",
        customer_id="cid-123",
        ad_group_id=1001,
        keyword_text="fryzjer warszawa",
        match_type="EXACT",
    )
    pause_calls = [c for c in fake.calls if c["method"] == "pause_ad_group_keyword_by_text"]
    assert len(pause_calls) == 1
    assert pause_calls[0]["keyword_text"] == "fryzjer warszawa"
    assert pause_calls[0]["match_type"] == "EXACT"
    assert pause_calls[0]["ad_group_id"] == 1001
