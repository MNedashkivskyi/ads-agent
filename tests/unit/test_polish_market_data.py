"""Tests for Polish market benchmarks, city tiers, and seasonality."""

from __future__ import annotations

import pytest

from adcopilot.domain.polish_market.city_tiers import classify_city
from adcopilot.domain.polish_market.cpc_benchmarks import BENCHMARKS, get_benchmark
from adcopilot.domain.polish_market.seasonality import get_seasonal_multiplier

VERTICALS = [
    "salon",
    "restauracja",
    "prawnik",
    "lekarz",
    "e-commerce",
    "nieruchomości",
    "edukacja",
    "usługi domowe",
]


def test_city_tier_warsaw_is_1() -> None:
    assert classify_city("Warszawa") == 1


def test_city_tier_gdansk_is_2() -> None:
    assert classify_city("Gdańsk") == 2


def test_city_tier_unknown_is_3() -> None:
    assert classify_city("Radom") == 3


@pytest.mark.parametrize("vertical", VERTICALS)
def test_all_verticals_have_3_tiers(vertical: str) -> None:
    for tier in (1, 2, 3):
        assert (vertical, tier) in BENCHMARKS, f"Missing ({vertical}, {tier})"


@pytest.mark.parametrize("vertical", VERTICALS)
def test_get_benchmark_warsaw(vertical: str) -> None:
    b = get_benchmark(vertical, "Warszawa")
    assert b is not None
    assert b.city_tier == 1
    assert b.avg_cpc_pln > 0
    assert b.min_monthly_budget_pln > 0
    assert b.recommended_monthly_budget_pln >= b.min_monthly_budget_pln


def test_get_benchmark_returns_none_for_unknown_vertical() -> None:
    assert get_benchmark("unknown_vertical", "Warszawa") is None


@pytest.mark.parametrize("vertical", VERTICALS)
def test_seasonality_has_12_months(vertical: str) -> None:
    for month in range(1, 13):
        m = get_seasonal_multiplier(vertical, month)
        assert 0.5 <= m <= 2.0, f"Unexpected multiplier {m} for {vertical} month {month}"


def test_seasonality_salon_december_peak() -> None:
    dec = get_seasonal_multiplier("salon", 12)
    jan = get_seasonal_multiplier("salon", 1)
    assert dec > jan


def test_seasonality_unknown_vertical_returns_1() -> None:
    assert get_seasonal_multiplier("unknown", 6) == 1.0
