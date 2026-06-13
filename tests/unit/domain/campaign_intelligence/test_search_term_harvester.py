"""Phase 5.1 — search-term harvester: promote winners, flag waste, dedupe."""

from __future__ import annotations

from adcopilot.domain.campaign_intelligence.keywords.search_term import (
    NEGATIVE,
    PROMOTE,
    SearchTerm,
    harvest,
)


def _term(term: str, *, impressions=1000, clicks=0, conversions=0.0, cost=0) -> SearchTerm:
    return SearchTerm(
        term=term,
        matched_keyword="drenaż limfatyczny",
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
        cost_micros=cost,
        intent="INTENT",
    )


def test_high_performing_non_keyword_is_promoted() -> None:
    terms = [_term("masaż wyszczuplający", clicks=40, conversions=5.0)]
    result = harvest(terms, existing_keywords=set())
    assert len(result.promotions) == 1
    assert result.promotions[0].term == "masaż wyszczuplający"
    assert result.promotions[0].kind == PROMOTE
    assert result.promotions[0].intent == "INTENT"


def test_strong_intent_without_conversion_is_promoted() -> None:
    # High CTR with enough clicks → promote even before a conversion lands.
    terms = [_term("drenaż nóg cena", impressions=400, clicks=40, conversions=0.0)]
    result = harvest(terms, existing_keywords=set())
    assert [p.term for p in result.promotions] == ["drenaż nóg cena"]


def test_high_spend_zero_conversion_flagged_negative() -> None:
    terms = [_term("praca drenaż magazyn", clicks=50, conversions=0.0, cost=30_000_000)]
    result = harvest(terms, existing_keywords=set())
    assert len(result.negatives) == 1
    assert result.negatives[0].kind == NEGATIVE
    assert not result.promotions


def test_existing_keyword_not_reproposed() -> None:
    terms = [_term("drenaż limfatyczny", clicks=40, conversions=5.0)]
    result = harvest(terms, existing_keywords={"drenaż limfatyczny"})
    assert result.promotions == []
    assert result.negatives == []


def test_dedupes_repeated_terms() -> None:
    terms = [
        _term("masaż", clicks=40, conversions=5.0),
        _term("masaż", clicks=20, conversions=2.0),
    ]
    result = harvest(terms, existing_keywords=set())
    assert len(result.promotions) == 1
