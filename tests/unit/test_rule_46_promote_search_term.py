"""Tests for Rule 46 — Promote High-Converting Search Term."""

from __future__ import annotations

from datetime import date, UTC, datetime
from uuid import uuid4

import pytest

from adcopilot.application.detection.base import DetectionContext, HistoricalStats
from adcopilot.application.detection.rules.rule_46_promote_search_term import (
    PromoteSearchTermRule,
    _jaccard,
    _is_already_keyword,
)
from adcopilot.domain.entities import AccountId, GoogleAdsAccount, UserId
from adcopilot.domain.recommendation import RecommendationKind
from adcopilot.domain.snapshot import KeywordSnapshot, SearchTermSnapshot, SnapshotId


def _account() -> GoogleAdsAccount:
    from datetime import datetime, UTC
    return GoogleAdsAccount(
        id=AccountId("123"),
        user_id=UserId("u1"),
        customer_id="123",
        descriptive_name="Test",
        currency="PLN",
        timezone="Europe/Warsaw",
        is_manager=False,
        write_enabled=True,
        connected_at=datetime.now(UTC),
    )


def _history(avg_cpa_micros: int = 5_000_000) -> HistoricalStats:
    return HistoricalStats(
        avg_cpa_micros=avg_cpa_micros,
        total_cost_micros=50_000_000,
        total_conversions=10.0,
    )


def _ctx(
    search_terms: list[SearchTermSnapshot],
    keywords: list[KeywordSnapshot] | None = None,
    avg_cpa_micros: int = 5_000_000,
) -> DetectionContext:
    return DetectionContext(
        account=_account(),
        campaigns=[],
        ad_groups=[],
        keywords=keywords or [],
        search_terms=search_terms,
        ads=[],
        history=_history(avg_cpa_micros),
        snapshot_date=date.today(),
    )


def _st(
    term: str = "fryzjer warszawa",
    conversions: float = 5.0,
    clicks: int = 20,
    cost_micros: int = 20_000_000,
    ad_group_id: int = 1001,
) -> SearchTermSnapshot:
    return SearchTermSnapshot(
        id=SnapshotId(str(uuid4())),
        account_id=AccountId("123"),
        snapshot_date=date.today(),
        search_term=term,
        ad_group_id=ad_group_id,
        impressions=100,
        clicks=clicks,
        cost_micros=cost_micros,
        conversions=conversions,
        matched_keyword_id=None,
    )


def _kw(text: str) -> KeywordSnapshot:
    return KeywordSnapshot(
        id=SnapshotId(str(uuid4())),
        account_id=AccountId("123"),
        snapshot_date=date.today(),
        criterion_id=1,
        ad_group_id=1001,
        text=text,
        match_type="PHRASE",
        status="ENABLED",
        quality_score=7,
        impressions=500,
        clicks=50,
        cost_micros=50_000_000,
        conversions=10.0,
        ctr=0.1,
        avg_cpc_micros=1_000_000,
    )


# ---------------------------------------------------------------------------
# Jaccard helper tests
# ---------------------------------------------------------------------------


def test_jaccard_identical_strings() -> None:
    assert _jaccard("fryzjer warszawa", "fryzjer warszawa") == 1.0


def test_jaccard_completely_different() -> None:
    assert _jaccard("fryzjer", "dentist") == 0.0


def test_jaccard_partial_overlap() -> None:
    score = _jaccard("fryzjer warszawa centrum", "fryzjer centrum")
    assert 0.5 <= score < 1.0


def test_is_already_keyword_exact_match() -> None:
    assert _is_already_keyword("fryzjer warszawa", ["fryzjer warszawa", "salon"])


def test_is_already_keyword_no_match() -> None:
    assert not _is_already_keyword("dentysta kraków", ["fryzjer", "salon"])


# ---------------------------------------------------------------------------
# Rule detection tests
# ---------------------------------------------------------------------------


def test_term_with_5_conversions_triggers() -> None:
    rule = PromoteSearchTermRule()
    ctx = _ctx([_st(conversions=5.0, clicks=10)])
    recs = rule.detect(ctx)
    assert len(recs) == 1
    assert recs[0].kind == RecommendationKind.PROMOTE_SEARCH_TERM
    assert recs[0].payload["search_term"] == "fryzjer warszawa"
    assert recs[0].payload["suggested_match_type"] == "EXACT"


def test_term_with_2_conversions_does_not_trigger() -> None:
    rule = PromoteSearchTermRule()
    ctx = _ctx([_st(conversions=2.0, clicks=10)])
    recs = rule.detect(ctx)
    assert recs == []


def test_term_with_fewer_than_5_clicks_does_not_trigger() -> None:
    rule = PromoteSearchTermRule()
    ctx = _ctx([_st(conversions=5.0, clicks=3)])
    recs = rule.detect(ctx)
    assert recs == []


def test_term_already_as_keyword_does_not_trigger() -> None:
    rule = PromoteSearchTermRule()
    ctx = _ctx(
        search_terms=[_st(term="fryzjer warszawa")],
        keywords=[_kw("fryzjer warszawa")],
    )
    recs = rule.detect(ctx)
    assert recs == []


def test_term_similar_to_existing_keyword_skipped() -> None:
    """Term with Jaccard ≥0.8 vs an existing keyword should be skipped."""
    rule = PromoteSearchTermRule()
    ctx = _ctx(
        search_terms=[_st(term="najlepszy fryzjer warszawa")],
        keywords=[_kw("fryzjer najlepszy warszawa")],
    )
    recs = rule.detect(ctx)
    assert recs == []


def test_expensive_term_cpa_filter() -> None:
    """Term with CPA > 120% of avg should be filtered out."""
    rule = PromoteSearchTermRule()
    # avg CPA = 5 PLN, term CPA = 10 PLN (200%)
    ctx = _ctx(
        search_terms=[_st(conversions=5.0, clicks=10, cost_micros=50_000_000)],
        avg_cpa_micros=5_000_000,
    )
    recs = rule.detect(ctx)
    assert recs == []


def test_no_search_terms_returns_empty() -> None:
    rule = PromoteSearchTermRule()
    ctx = _ctx([])
    assert rule.detect(ctx) == []


def test_payload_contains_expected_fields() -> None:
    rule = PromoteSearchTermRule()
    ctx = _ctx([_st(conversions=4.0, clicks=10, cost_micros=12_000_000, ad_group_id=999)])
    recs = rule.detect(ctx)
    assert len(recs) == 1
    payload = recs[0].payload
    assert payload["suggested_ad_group_id"] == 999
    assert payload["conversions"] == 4.0
    assert payload["cpa_micros"] == 3_000_000


def test_duplicate_terms_deduplicated() -> None:
    rule = PromoteSearchTermRule()
    ctx = _ctx([
        _st(term="salon beauty", conversions=5.0, clicks=10),
        _st(term="salon beauty", conversions=5.0, clicks=10),
    ])
    recs = rule.detect(ctx)
    assert len(recs) == 1
