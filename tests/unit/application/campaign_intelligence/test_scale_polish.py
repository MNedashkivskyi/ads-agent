"""Phase 7 — cross-tenant safety, generation caching, per-language, rationale, guardrails."""

from __future__ import annotations

from datetime import date

from adcopilot.application.ports.cie_performance import PerformanceFact
from adcopilot.application.use_cases.campaign_intelligence.shared.recompute_dimension_weights import (  # noqa: E501
    RecomputeDimensionWeightsUseCase,
)
from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import (
    KeywordCandidate,
    KeywordStatus,
)
from adcopilot.domain.campaign_intelligence.keywords.keyword_comparison import build_comparison
from adcopilot.domain.campaign_intelligence.keywords.value_objects import (
    KeywordIntent,
    SearchVolume,
)
from adcopilot.domain.campaign_intelligence.shared import guardrails
from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    MIN_SAMPLE,
    DimensionPerformance,
)
from adcopilot.infrastructure.cache.generation_cache import CachingKeywordGenerator
from tests.unit.application.campaign_intelligence._fakes import (
    FakeDimensionPerformanceRepository,
    FakeFactRepository,
    FakeKeywordGenerator,
    FakeRedis,
)

_DAY = date(2026, 6, 1)


# --- 7.1 Cross-tenant aggregation safety ------------------------------------


async def test_cross_tenant_aggregation_leaks_no_literal_text() -> None:
    facts = FakeFactRepository()
    # Two different tenants in the same vertical, each with secret literal text.
    await facts.upsert_facts(
        [
            PerformanceFact(
                account_id="acct-A", customer_id="111", entity_type="keyword",
                entity_id="kA", day=_DAY, dimension="keyword_intent", value="PROBLEM",
                vertical="salon", language="pl", impressions=30_000, clicks=3000,
                conversions=300, cost_micros=0,
                extra={"text": "SECRET_ACCT_A_keyword_icoone"},
            ),
            PerformanceFact(
                account_id="acct-B", customer_id="222", entity_type="keyword",
                entity_id="kB", day=_DAY, dimension="keyword_intent", value="PROBLEM",
                vertical="salon", language="pl", impressions=30_000, clicks=2000,
                conversions=150, cost_micros=0,
                extra={"text": "SECRET_ACCT_B_competitor_brand"},
            ),
        ]
    )
    dim_repo = FakeDimensionPerformanceRepository()
    await RecomputeDimensionWeightsUseCase(facts, dim_repo).run(("keyword_intent",))

    perf = await dim_repo.get_map(vertical="salon", dimension="keyword_intent")
    blob = repr(perf)
    # Pooled learning exposes only dimension-level metrics — never raw text.
    assert "SECRET_ACCT_A" not in blob
    assert "SECRET_ACCT_B" not in blob
    assert perf["PROBLEM"].value == "PROBLEM"
    # The aggregate pooled both tenants (sample_size = sum of both).
    assert perf["PROBLEM"].sample_size == 60_000


# --- 7.2 Generation caching -------------------------------------------------


async def test_generation_cache_avoids_second_llm_call() -> None:
    inner = FakeKeywordGenerator()
    cached = CachingKeywordGenerator(inner, FakeRedis(), ttl_seconds=3600)
    args = dict(service="icoone", vertical="salon", problems=["cellulit"],
                intent_allocation={"INTENT": 2, "PROBLEM": 2, "BRAND": 1}, language="pl")

    first = await cached.generate(**args)
    second = await cached.generate(**args)  # identical → cache hit
    assert first == second
    assert len(inner.calls) == 1  # the wrapped generator was invoked only once

    # Different inputs miss the cache.
    await cached.generate(**{**args, "service": "inny zabieg"})
    assert len(inner.calls) == 2


# --- 7.3 Per-language weights -----------------------------------------------


async def test_weights_diverge_by_language() -> None:
    facts = FakeFactRepository()
    await facts.upsert_facts(
        [
            # PL: PROBLEM converts best.
            PerformanceFact(account_id="a", customer_id="1", entity_type="keyword",
                            entity_id="p1", day=_DAY, dimension="keyword_intent", value="PROBLEM",
                            vertical="salon", language="pl", impressions=40_000, clicks=4000,
                            conversions=600, cost_micros=0),
            PerformanceFact(account_id="a", customer_id="1", entity_type="keyword",
                            entity_id="i1", day=_DAY, dimension="keyword_intent", value="INTENT",
                            vertical="salon", language="pl", impressions=40_000, clicks=4000,
                            conversions=200, cost_micros=0),
            # UK: INTENT converts best (the opposite).
            PerformanceFact(account_id="a", customer_id="1", entity_type="keyword",
                            entity_id="p2", day=_DAY, dimension="keyword_intent", value="PROBLEM",
                            vertical="salon", language="uk", impressions=40_000, clicks=4000,
                            conversions=200, cost_micros=0),
            PerformanceFact(account_id="a", customer_id="1", entity_type="keyword",
                            entity_id="i2", day=_DAY, dimension="keyword_intent", value="INTENT",
                            vertical="salon", language="uk", impressions=40_000, clicks=4000,
                            conversions=600, cost_micros=0),
        ]
    )
    dim_repo = FakeDimensionPerformanceRepository()
    await RecomputeDimensionWeightsUseCase(facts, dim_repo).run(("keyword_intent",))

    pl = await dim_repo.get_map(vertical="salon", dimension="keyword_intent", language="pl")
    uk = await dim_repo.get_map(vertical="salon", dimension="keyword_intent", language="uk")
    assert pl["PROBLEM"].smoothed_score > pl["INTENT"].smoothed_score
    assert uk["INTENT"].smoothed_score > uk["PROBLEM"].smoothed_score  # diverges independently


# --- 7.4 "Why this?" rationale ----------------------------------------------


def test_comparison_includes_rationale_when_learned() -> None:
    c = KeywordCandidate(
        phrase="drenaż limfatyczny", intent=KeywordIntent.PROBLEM,
        volume=SearchVolume(monthly_searches=8000, competition="MEDIUM"),
    )
    c.status = KeywordStatus.VALIDATED
    perf = {
        "PROBLEM": DimensionPerformance(
            vertical="salon", dimension="keyword_intent", value="PROBLEM",
            sample_size=MIN_SAMPLE * 10, clicks=5000, conversions=600,
            weighted_ctr=0.05, weighted_conv=0.12, smoothed_score=0.2,
        )
    }
    comparison = build_comparison([c], performance=perf)
    problem_group = next(g for g in comparison.groups if g.intent == "PROBLEM")
    assert problem_group.rationale  # rationale present
    assert "PROBLEM" in problem_group.rationale

    # Without learned data, no rationale (cold start).
    assert build_comparison([c]).groups[0].rationale == ""


# --- 7.5 Guardrails ----------------------------------------------------------


def test_guardrails_flag_starved_and_drift() -> None:
    perfs = [
        DimensionPerformance(
            vertical="salon", dimension="keyword_intent", value="BRAND",
            sample_size=50, clicks=2, conversions=0, weighted_ctr=0.04,
            weighted_conv=0.0, smoothed_score=0.05,
        ),
        DimensionPerformance(
            vertical="salon", dimension="keyword_intent", value="PROBLEM",
            sample_size=MIN_SAMPLE * 10, clicks=5000, conversions=600,
            weighted_ctr=0.05, weighted_conv=0.12, smoothed_score=0.30,
        ),
    ]
    previous = {"salon:keyword_intent:PROBLEM:pl": 0.10}  # was 0.10, now 0.30 → +200%
    alerts = guardrails.check_guardrails(perfs, previous)
    kinds = {(a.kind, a.value) for a in alerts}
    assert (guardrails.STARVED, "BRAND") in kinds  # below MIN_SAMPLE
    assert (guardrails.DRIFT, "PROBLEM") in kinds  # moved > 50%


def test_guardrails_quiet_when_healthy() -> None:
    perfs = [
        DimensionPerformance(
            vertical="salon", dimension="keyword_intent", value="PROBLEM",
            sample_size=MIN_SAMPLE * 10, clicks=5000, conversions=600,
            weighted_ctr=0.05, weighted_conv=0.12, smoothed_score=0.30,
        )
    ]
    previous = {"salon:keyword_intent:PROBLEM:pl": 0.29}  # tiny change
    assert guardrails.check_guardrails(perfs, previous) == []
