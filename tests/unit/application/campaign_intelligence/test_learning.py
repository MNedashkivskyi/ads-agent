"""Phase 6 — recompute weights, learned-weight injection, cold start, backtest."""

from __future__ import annotations

from datetime import date, timedelta

from adcopilot.application.ports.cie_performance import PerformanceFact
from adcopilot.application.use_cases.campaign_intelligence.shared.recompute_dimension_weights import (  # noqa: E501
    RecomputeDimensionWeightsUseCase,
)
from adcopilot.domain.campaign_intelligence.keywords import keyword_scorer
from adcopilot.domain.campaign_intelligence.keywords.value_objects import (
    KeywordIntent,
    SearchVolume,
)
from adcopilot.domain.campaign_intelligence.shared import dimension_selector
from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    MIN_SAMPLE,
    DimensionPerformance,
)
from adcopilot.domain.campaign_intelligence.shared.learned_weights import (
    weights_from_performance,
)
from tests.unit.application.campaign_intelligence._fakes import (
    FakeDimensionPerformanceRepository,
    FakeFactRepository,
)

_DAY = date(2026, 6, 1)
_ACCOUNT = "11111111-1111-1111-1111-111111111111"


def _fact(dimension: str, value: str, *, impr: int, clicks: int, conv: float, day=_DAY,
          entity="e") -> PerformanceFact:
    etype = "keyword" if dimension == "keyword_intent" else "asset"
    return PerformanceFact(
        account_id=_ACCOUNT, customer_id="123", entity_type=etype,
        entity_id=f"{value}-{entity}-{day}", day=day, dimension=dimension, value=value,
        vertical="salon", language="pl", impressions=impr, clicks=clicks,
        conversions=conv, cost_micros=0,
    )


async def test_recompute_writes_both_dimensions() -> None:
    facts = FakeFactRepository()
    await facts.upsert_facts(
        [
            _fact("keyword_intent", "PROBLEM", impr=50_000, clicks=5000, conv=500),
            _fact("keyword_intent", "BRAND", impr=50_000, clicks=2000, conv=50),
            _fact("angle", "PAIN", impr=50_000, clicks=4000, conv=400),
            _fact("angle", "RESULT", impr=50_000, clicks=2000, conv=80),
        ]
    )
    dim_repo = FakeDimensionPerformanceRepository()
    written = await RecomputeDimensionWeightsUseCase(facts, dim_repo).run()
    assert written["keyword_intent"] == 2
    assert written["angle"] == 2

    kw = await dim_repo.get_map(vertical="salon", dimension="keyword_intent")
    assert kw["PROBLEM"].smoothed_score > kw["BRAND"].smoothed_score


async def test_small_sample_smoothed_and_gated_out() -> None:
    facts = FakeFactRepository()
    await facts.upsert_facts(
        [
            # A 3-impression fluke (100% conversion) vs a well-measured value.
            _fact("keyword_intent", "PROBLEM", impr=3, clicks=3, conv=3, entity="tiny"),
            _fact("keyword_intent", "INTENT", impr=50_000, clicks=5000, conv=500, entity="big"),
        ]
    )
    dim_repo = FakeDimensionPerformanceRepository()
    await RecomputeDimensionWeightsUseCase(facts, dim_repo).run()
    kw = await dim_repo.get_map(vertical="salon", dimension="keyword_intent")
    # Smoothing shrinks the 100%-on-3-clicks rate hard toward the prior
    # (a raw combined score would be ~1.2; smoothed it is far lower).
    assert kw["PROBLEM"].weighted_conv == 1.0  # observed
    assert kw["PROBLEM"].smoothed_score < 0.4  # heavily shrunk
    # And the real guard: below MIN_SAMPLE the fluke is excluded from the
    # trusted weights entirely, so it can never out-weight a measured value.
    weights = weights_from_performance(kw)
    assert "PROBLEM" not in weights
    assert "INTENT" in weights


def _perf(value: str, *, impr: int, score: float) -> DimensionPerformance:
    return DimensionPerformance(
        vertical="salon", dimension="keyword_intent", value=value, sample_size=impr,
        clicks=int(impr * 0.05), conversions=impr * 0.005, weighted_ctr=0.05,
        weighted_conv=0.1, smoothed_score=score,
    )


def test_learned_weights_inject_into_scorer() -> None:
    perf = {
        "PROBLEM": _perf("PROBLEM", impr=MIN_SAMPLE * 10, score=0.20),
        "BRAND": _perf("BRAND", impr=MIN_SAMPLE * 10, score=0.05),
    }
    weights = weights_from_performance(perf)
    vol = SearchVolume(monthly_searches=1000, competition="MEDIUM")
    problem = keyword_scorer.compute_score(
        vol, keyword_scorer.intent_weight_for(KeywordIntent.PROBLEM, weights)
    )
    brand = keyword_scorer.compute_score(
        vol, keyword_scorer.intent_weight_for(KeywordIntent.BRAND, weights)
    )
    assert problem.value > brand.value  # learned winner scores higher


def test_removing_learned_data_reverts_to_static_no_crash() -> None:
    # Empty learned weights → scorer falls back to static priors, no error.
    weights = weights_from_performance({})
    assert weights == {}
    w = keyword_scorer.intent_weight_for(KeywordIntent.PROBLEM, weights)
    assert w == KeywordIntent.PROBLEM.default_weight


def test_cold_start_below_min_sample_is_uniform() -> None:
    # A vertical whose only data is below MIN_SAMPLE behaves as a pure generator.
    perf = {"PROBLEM": _perf("PROBLEM", impr=MIN_SAMPLE - 1, score=99.0)}
    assert weights_from_performance(perf) == {}  # untrusted → omitted
    alloc = dimension_selector.allocate(9, ["BRAND", "INTENT", "PROBLEM"], perf)
    assert alloc == {"BRAND": 3, "INTENT": 3, "PROBLEM": 3}  # uniform


def test_crossing_min_sample_flips_to_learned() -> None:
    perf = {
        "BRAND": _perf("BRAND", impr=MIN_SAMPLE * 5, score=0.05),
        "INTENT": _perf("INTENT", impr=MIN_SAMPLE * 5, score=0.10),
        "PROBLEM": _perf("PROBLEM", impr=MIN_SAMPLE * 5, score=0.20),
    }
    alloc = dimension_selector.allocate(30, ["BRAND", "INTENT", "PROBLEM"], perf)
    assert alloc["PROBLEM"] > alloc["BRAND"]  # learned weighting in effect


# ---------------------------------------------------------------------------
# Backtest harness (6.4) — replay history; winners trend up, no collapse.
# ---------------------------------------------------------------------------


async def test_backtest_winner_trends_up_without_collapse() -> None:
    """Replay 4 periods; PROBLEM converts best each period. Its slot share should
    rise across periods while losers keep at least the explore floor."""
    facts = FakeFactRepository()
    dim_repo = FakeDimensionPerformanceRepository()
    values = ["BRAND", "INTENT", "PROBLEM"]
    shares: list[dict[str, int]] = []

    for period in range(4):
        day = _DAY + timedelta(days=period)
        # Accumulate more converting data for PROBLEM each period.
        await facts.upsert_facts(
            [
                _fact("keyword_intent", "BRAND", impr=20_000, clicks=400, conv=10, day=day),
                _fact("keyword_intent", "INTENT", impr=20_000, clicks=800, conv=40, day=day),
                _fact("keyword_intent", "PROBLEM", impr=20_000, clicks=1600,
                      conv=120 + period * 40, day=day),
            ]
        )
        await RecomputeDimensionWeightsUseCase(facts, dim_repo).run(("keyword_intent",))
        perf = await dim_repo.get_map(vertical="salon", dimension="keyword_intent")
        shares.append(dimension_selector.allocate(30, values, perf))

    # PROBLEM's share trends up from first to last period.
    assert shares[-1]["PROBLEM"] >= shares[0]["PROBLEM"]
    assert shares[-1]["PROBLEM"] == max(shares[-1].values())
    # No collapse — every value keeps at least the explore floor throughout.
    assert all(all(v >= 1 for v in s.values()) for s in shares)
