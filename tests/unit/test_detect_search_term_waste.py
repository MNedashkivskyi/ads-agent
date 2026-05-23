"""Unit tests for detect_search_term_waste use case."""

from __future__ import annotations

from datetime import date

from adcopilot.application.use_cases.detect_search_term_waste import detect_search_term_waste
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import RecommendationKind, RecommendationSeverity
from adcopilot.domain.snapshot import SearchTermSnapshot


def _term(search_term: str, cost_micros: int, conversions: float = 0.0) -> SearchTermSnapshot:
    return SearchTermSnapshot(
        id="snap-1",  # type: ignore[arg-type]
        account_id=AccountId("acc-1"),
        snapshot_date=date(2026, 1, 1),
        search_term=search_term,
        ad_group_id=1,
        impressions=100,
        clicks=10,
        cost_micros=cost_micros,
        conversions=conversions,
        matched_keyword_id=None,
        campaign_name="Test Campaign",
    )


ACCOUNT = AccountId("acc-1")


def test_no_terms_returns_empty() -> None:
    assert detect_search_term_waste(ACCOUNT, []) == []


def test_zero_total_cost_returns_empty() -> None:
    terms = [_term("foo", 0), _term("bar", 0)]
    assert detect_search_term_waste(ACCOUNT, terms) == []


def test_term_with_conversions_not_flagged() -> None:
    terms = [_term("foo", 900_000, conversions=1.0), _term("bar", 100_000)]
    recs = detect_search_term_waste(ACCOUNT, terms)
    assert all(r.evidence["search_term"] != "foo" for r in recs)


def test_term_below_threshold_not_flagged() -> None:
    # "cheap" is 10% of total — below 20% threshold
    terms = [_term("cheap", 100_000), _term("expensive", 900_000, conversions=5.0)]
    recs = detect_search_term_waste(ACCOUNT, terms)
    assert recs == []


def test_wasteful_term_above_threshold_flagged() -> None:
    # "waste" consumes 50% of budget with 0 conversions
    terms = [_term("waste", 500_000), _term("good", 500_000, conversions=3.0)]
    recs = detect_search_term_waste(ACCOUNT, terms)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.kind == RecommendationKind.SEARCH_TERM_WASTE
    assert rec.severity == RecommendationSeverity.HIGH
    assert rec.evidence["search_term"] == "waste"
    assert rec.evidence["waste_pct"] == 50.0
    assert rec.evidence["conversions"] == 0
    assert rec.estimated_monthly_savings_micros == 500_000 * 30


def test_exactly_at_threshold_not_flagged() -> None:
    # exactly 20% → not > 20%
    terms = [_term("borderline", 200_000), _term("other", 800_000, conversions=1.0)]
    recs = detect_search_term_waste(ACCOUNT, terms)
    assert recs == []


def test_multiple_wasteful_terms_all_flagged() -> None:
    terms = [
        _term("waste1", 400_000),
        _term("waste2", 350_000),
        _term("good", 250_000, conversions=2.0),
    ]
    recs = detect_search_term_waste(ACCOUNT, terms)
    flagged = {r.evidence["search_term"] for r in recs}
    assert flagged == {"waste1", "waste2"}


def test_recommendation_target_matches_account() -> None:
    terms = [_term("waste", 600_000), _term("ok", 400_000, conversions=1.0)]
    recs = detect_search_term_waste(ACCOUNT, terms)
    assert recs[0].account_id == ACCOUNT
