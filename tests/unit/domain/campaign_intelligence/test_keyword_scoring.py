"""Phase 1 — keyword value objects, scorer, and the brand-vs-intent comparison."""

from __future__ import annotations

from adcopilot.domain.campaign_intelligence.keywords import keyword_scorer
from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import (
    KeywordCandidate,
    KeywordStatus,
)
from adcopilot.domain.campaign_intelligence.keywords.keyword_comparison import build_comparison
from adcopilot.domain.campaign_intelligence.keywords.value_objects import (
    MIN_VIABLE_VOLUME,
    KeywordIntent,
    SearchVolume,
)
from adcopilot.infrastructure.prompts import keyword_generation


def _vol(searches: int, competition: str = "MEDIUM", bucketed: bool = False) -> SearchVolume:
    return SearchVolume(
        monthly_searches=searches, competition=competition, is_bucketed=bucketed
    )


def test_search_volume_viability_and_bucketed() -> None:
    assert _vol(MIN_VIABLE_VOLUME).is_viable
    assert not _vol(MIN_VIABLE_VOLUME - 1).is_viable
    assert _vol(0).is_viable is False
    assert _vol(100, bucketed=True).is_bucketed


def test_keyword_intent_has_three_values() -> None:
    assert {i.value for i in KeywordIntent} == {"BRAND", "INTENT", "PROBLEM"}
    assert KeywordIntent.PROBLEM.default_weight > KeywordIntent.BRAND.default_weight


def test_zero_volume_scores_zero_and_rejects() -> None:
    c = KeywordCandidate(phrase="x", intent=KeywordIntent.INTENT, volume=_vol(0))
    c.status = KeywordStatus.VALIDATED
    score = keyword_scorer.score_candidate(c)
    assert score.value == 0.0
    assert c.status is KeywordStatus.REJECTED


def test_problem_intent_outrank_brand_at_equal_volume() -> None:
    vol = _vol(1000)
    brand = keyword_scorer.compute_score(vol, KeywordIntent.BRAND.default_weight)
    intent = keyword_scorer.compute_score(vol, KeywordIntent.INTENT.default_weight)
    problem = keyword_scorer.compute_score(vol, KeywordIntent.PROBLEM.default_weight)
    assert problem.value >= intent.value > brand.value


def test_scorer_is_deterministic() -> None:
    vol = _vol(5000, competition="LOW")
    a = keyword_scorer.compute_score(vol, 1.2)
    b = keyword_scorer.compute_score(vol, 1.2)
    assert a == b


def test_learned_weight_overrides_static_prior() -> None:
    vol = _vol(1000)
    w = keyword_scorer.intent_weight_for(KeywordIntent.BRAND, {"BRAND": 5.0})
    assert w == 5.0
    # without a learned entry, falls back to the static prior
    assert keyword_scorer.intent_weight_for(KeywordIntent.BRAND, {}) == KeywordIntent.BRAND.default_weight


# ---------------------------------------------------------------------------
# Comparison — the icoone proof
# ---------------------------------------------------------------------------


def _validated(phrase: str, intent: KeywordIntent, searches: int) -> KeywordCandidate:
    c = KeywordCandidate(phrase=phrase, intent=intent, volume=_vol(searches))
    c.status = KeywordStatus.VALIDATED
    return c


def test_comparison_groups_and_icoone_verdict() -> None:
    candidates = [
        _validated("icoone warszawa", KeywordIntent.BRAND, 30),
        _validated("icoone cena", KeywordIntent.BRAND, 20),
        _validated("drenaż limfatyczny", KeywordIntent.INTENT, 8000),
        _validated("modelowanie sylwetki", KeywordIntent.INTENT, 4000),
        _validated("jak pozbyć się cellulitu", KeywordIntent.PROBLEM, 6000),
    ]
    comparison = build_comparison(candidates)

    by_intent = {g.intent: g for g in comparison.groups}
    assert by_intent["BRAND"].keyword_count == 2
    assert by_intent["INTENT"].keyword_count == 2
    assert by_intent["PROBLEM"].keyword_count == 1
    # INTENT/PROBLEM volume dwarfs BRAND — the whole point.
    assert comparison.intent_total_volume > comparison.brand_total_volume * 100
    assert comparison.multiplier > 100
    assert comparison.verdict  # non-empty Polish verdict string


def test_comparison_no_data_verdict() -> None:
    comparison = build_comparison([])
    assert comparison.brand_total_volume == 0
    assert comparison.intent_total_volume == 0
    assert "Brak danych" in comparison.verdict


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


def test_keyword_generation_prompt_renders_without_leftover_placeholders() -> None:
    system, user = keyword_generation.render(
        service="icoone — modelowanie sylwetki",
        vertical="salon",
        problems=["cellulit po ciąży", "nie mogę schudnąć z ud"],
        intent_allocation={"BRAND": 3, "INTENT": 4, "PROBLEM": 3},
        language="pl",
    )
    assert "icoone — modelowanie sylwetki" in user
    assert "salon" in user
    assert "cellulit po ciąży" in user
    # All single-brace placeholders resolved (literal JSON braces were doubled).
    assert "{service}" not in user
    assert "{vertical}" not in user
    assert "{allocation}" not in user
    assert "{problems}" not in user
    assert system  # system prompt present
