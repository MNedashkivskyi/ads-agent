"""Phase 0 — lock the generic spine's behaviour.

Covers the shared value objects, Bayesian smoothing, the DimensionPerformance
entity, and the explore/exploit selector (cold start, winner up-weighting, floor,
small-sample protection).
"""

from __future__ import annotations

import pytest

from adcopilot.domain.campaign_intelligence.shared import bayesian_smoothing, dimension_selector
from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    MIN_SAMPLE,
    DimensionPerformance,
)
from adcopilot.domain.campaign_intelligence.shared.performance_label import PerformanceLabel
from adcopilot.domain.campaign_intelligence.shared.strategic_dimension import (
    StrategicDimension,
    dimension_values,
)
from adcopilot.domain.campaign_intelligence.shared.vertical import (
    InvalidVerticalError,
    Vertical,
    VerticalTaxonomy,
)


# ---------------------------------------------------------------------------
# Vertical
# ---------------------------------------------------------------------------


def test_vertical_parse_canonical() -> None:
    assert Vertical.parse("salon").value is VerticalTaxonomy.SALON
    assert Vertical.parse("MEDICAL").value is VerticalTaxonomy.MEDICAL


def test_vertical_parse_alias_normalises() -> None:
    # YAML slugs and Polish aliases collapse onto the canonical taxonomy.
    assert Vertical.parse("beauty_salon").value is VerticalTaxonomy.SALON
    assert Vertical.parse("dental_clinic").value is VerticalTaxonomy.MEDICAL
    assert Vertical.parse("kancelaria").value is VerticalTaxonomy.LEGAL


def test_vertical_rejects_unknown_with_domain_error() -> None:
    with pytest.raises(InvalidVerticalError):
        Vertical.parse("crypto-casino")


def test_vertical_from_raw_is_lenient() -> None:
    assert Vertical.from_raw("crypto-casino").value is VerticalTaxonomy.GENERIC
    assert Vertical.from_raw(None).value is VerticalTaxonomy.GENERIC
    assert Vertical.from_raw("salon").value is VerticalTaxonomy.SALON


def test_vertical_is_frozen_and_value_equal() -> None:
    a = Vertical.parse("salon")
    b = Vertical.parse("salon")
    assert a == b
    assert hash(a) == hash(b)
    with pytest.raises(Exception):
        a.value = VerticalTaxonomy.LEGAL  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PerformanceLabel
# ---------------------------------------------------------------------------


def test_performance_label_parses_google_strings() -> None:
    assert PerformanceLabel.parse("BEST") is PerformanceLabel.BEST
    assert PerformanceLabel.parse("good") is PerformanceLabel.GOOD
    # Unknown / unspecified / empty all map to PENDING.
    assert PerformanceLabel.parse("UNKNOWN") is PerformanceLabel.PENDING
    assert PerformanceLabel.parse("UNSPECIFIED") is PerformanceLabel.PENDING
    assert PerformanceLabel.parse(None) is PerformanceLabel.PENDING
    assert PerformanceLabel.parse("") is PerformanceLabel.PENDING


def test_performance_label_is_orderable() -> None:
    assert PerformanceLabel.BEST > PerformanceLabel.GOOD > PerformanceLabel.LOW
    assert PerformanceLabel.LOW > PerformanceLabel.LEARNING > PerformanceLabel.PENDING
    ordered = sorted([PerformanceLabel.BEST, PerformanceLabel.PENDING, PerformanceLabel.GOOD])
    assert ordered == [PerformanceLabel.PENDING, PerformanceLabel.GOOD, PerformanceLabel.BEST]
    assert PerformanceLabel.BEST.is_rated
    assert not PerformanceLabel.PENDING.is_rated


# ---------------------------------------------------------------------------
# StrategicDimension protocol
# ---------------------------------------------------------------------------


def test_strategic_dimension_protocol_satisfied_by_enum() -> None:
    from adcopilot.domain.campaign_intelligence.keywords.value_objects import KeywordIntent

    member = KeywordIntent.PROBLEM
    assert isinstance(member, StrategicDimension)
    assert member.value == "PROBLEM"
    assert member.dimension_name == "keyword_intent"
    assert set(dimension_values(KeywordIntent)) == {"BRAND", "INTENT", "PROBLEM"}


# ---------------------------------------------------------------------------
# Bayesian smoothing
# ---------------------------------------------------------------------------


def test_smooth_rate_zero_sample_returns_prior() -> None:
    assert bayesian_smoothing.smooth_rate(0.9, 0, 0.05) == pytest.approx(0.05)


def test_smooth_rate_large_sample_converges_to_observed() -> None:
    smoothed = bayesian_smoothing.smooth_rate(0.30, 1_000_000, 0.05, prior_strength=30)
    assert smoothed == pytest.approx(0.30, abs=1e-3)


def test_smooth_rate_small_sample_pulled_toward_prior() -> None:
    # 3 clicks, 3 conversions = 100% observed, but heavily shrunk toward 5% prior.
    smoothed = bayesian_smoothing.smooth_rate(1.0, 3, 0.05, prior_strength=30)
    assert smoothed < 0.2


def test_smoothed_metrics_combines_rates() -> None:
    ctr, conv, score = bayesian_smoothing.smoothed_metrics(
        impressions=10_000,
        clicks=500,
        conversions=50,
        prior_ctr=0.04,
        prior_conv=0.05,
    )
    assert ctr == pytest.approx(0.05)
    assert conv == pytest.approx(0.10, abs=0.02)
    assert score > 0


# ---------------------------------------------------------------------------
# Selector — cold start, winner, floor, small-sample protection
# ---------------------------------------------------------------------------


def _perf(value: str, *, impressions: int, ctr: float, conv: float, score: float) -> DimensionPerformance:
    return DimensionPerformance(
        vertical="salon",
        dimension="keyword_intent",
        value=value,
        sample_size=impressions,
        clicks=int(impressions * ctr),
        conversions=impressions * ctr * conv,
        weighted_ctr=ctr,
        weighted_conv=conv,
        smoothed_score=score,
    )


VALUES = ["BRAND", "INTENT", "PROBLEM"]


def test_cold_start_returns_uniform() -> None:
    alloc = dimension_selector.allocate(9, VALUES, {})
    assert alloc == {"BRAND": 3, "INTENT": 3, "PROBLEM": 3}
    assert sum(alloc.values()) == 9


def test_winner_gets_more_slots_than_loser() -> None:
    perf = {
        "BRAND": _perf("BRAND", impressions=MIN_SAMPLE * 5, ctr=0.02, conv=0.01, score=0.02),
        "INTENT": _perf("INTENT", impressions=MIN_SAMPLE * 5, ctr=0.05, conv=0.05, score=0.06),
        "PROBLEM": _perf("PROBLEM", impressions=MIN_SAMPLE * 5, ctr=0.08, conv=0.12, score=0.14),
    }
    alloc = dimension_selector.allocate(30, VALUES, perf)
    assert sum(alloc.values()) == 30
    assert alloc["PROBLEM"] > alloc["INTENT"] > alloc["BRAND"]


def test_floor_never_violated() -> None:
    perf = {
        "BRAND": _perf("BRAND", impressions=MIN_SAMPLE * 5, ctr=0.0, conv=0.0, score=0.0001),
        "INTENT": _perf("INTENT", impressions=MIN_SAMPLE * 5, ctr=0.2, conv=0.3, score=0.9),
        "PROBLEM": _perf("PROBLEM", impressions=MIN_SAMPLE * 5, ctr=0.2, conv=0.3, score=0.9),
    }
    alloc = dimension_selector.allocate(20, VALUES, perf)
    assert all(slots >= 1 for slots in alloc.values())  # explore floor holds
    assert alloc["BRAND"] >= 1


def test_three_impression_value_cannot_outrank_50k_value() -> None:
    # A tiny-sample value below MIN_SAMPLE is treated as cold-start (neutral),
    # never dominating a well-measured 50k value with a slightly-better score.
    perf = {
        "BRAND": _perf("BRAND", impressions=50_000, ctr=0.06, conv=0.08, score=0.10),
        "INTENT": _perf("INTENT", impressions=50_000, ctr=0.06, conv=0.08, score=0.10),
        # 3 impressions, fluky perfect rate — but below MIN_SAMPLE, so untrusted.
        "PROBLEM": _perf("PROBLEM", impressions=3, ctr=1.0, conv=1.0, score=5.0),
    }
    alloc = dimension_selector.allocate(30, VALUES, perf)
    assert alloc["PROBLEM"] <= alloc["BRAND"]
    assert alloc["PROBLEM"] <= alloc["INTENT"]


def test_no_single_value_collapse() -> None:
    # Even with one runaway winner, exploration keeps losers above the floor.
    perf = {
        "BRAND": _perf("BRAND", impressions=MIN_SAMPLE * 5, ctr=0.0, conv=0.0, score=0.0),
        "INTENT": _perf("INTENT", impressions=MIN_SAMPLE * 5, ctr=0.0, conv=0.0, score=0.0),
        "PROBLEM": _perf("PROBLEM", impressions=MIN_SAMPLE * 5, ctr=0.5, conv=0.9, score=10.0),
    }
    alloc = dimension_selector.allocate(30, VALUES, perf)
    # Winner leads, but losers retain more than just the bare floor via exploration.
    assert alloc["PROBLEM"] == max(alloc.values())
    assert alloc["BRAND"] >= 1 and alloc["INTENT"] >= 1


def test_allocate_raises_when_too_few_slots_for_floor() -> None:
    with pytest.raises(ValueError):
        dimension_selector.allocate(2, VALUES, {})  # 2 < 3 values * floor 1


def test_allocate_empty_values() -> None:
    assert dimension_selector.allocate(5, [], {}) == {}
