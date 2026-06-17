"""Polish vertical CPC/CPA benchmarks by city tier."""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.domain.polish_market.city_tiers import classify_city


@dataclass(frozen=True)
class VerticalBenchmark:
    vertical: str
    city_tier: int
    avg_cpc_pln: float
    avg_cpa_pln: float
    avg_ctr_pct: float
    avg_conversion_rate_pct: float
    min_monthly_budget_pln: int
    recommended_monthly_budget_pln: int


# (vertical, city_tier) → VerticalBenchmark
BENCHMARKS: dict[tuple[str, int], VerticalBenchmark] = {
    # salon
    ("salon", 1): VerticalBenchmark("salon", 1, 2.5, 35, 3.2, 5.0, 500, 1500),
    ("salon", 2): VerticalBenchmark("salon", 2, 1.8, 25, 3.0, 5.0, 300, 1000),
    ("salon", 3): VerticalBenchmark("salon", 3, 1.2, 18, 2.8, 5.0, 200, 700),
    # restauracja
    ("restauracja", 1): VerticalBenchmark("restauracja", 1, 1.8, 20, 4.0, 6.0, 400, 1200),
    ("restauracja", 2): VerticalBenchmark("restauracja", 2, 1.3, 15, 3.8, 6.0, 250, 800),
    ("restauracja", 3): VerticalBenchmark("restauracja", 3, 0.9, 10, 3.5, 6.0, 150, 500),
    # prawnik
    ("prawnik", 1): VerticalBenchmark("prawnik", 1, 18.0, 250, 2.5, 2.0, 2000, 6000),
    ("prawnik", 2): VerticalBenchmark("prawnik", 2, 12.0, 180, 2.3, 2.0, 1500, 4000),
    ("prawnik", 3): VerticalBenchmark("prawnik", 3, 8.0, 120, 2.0, 2.0, 1000, 3000),
    # lekarz
    ("lekarz", 1): VerticalBenchmark("lekarz", 1, 6.0, 80, 3.0, 3.5, 800, 2500),
    ("lekarz", 2): VerticalBenchmark("lekarz", 2, 4.0, 55, 2.8, 3.5, 500, 1800),
    ("lekarz", 3): VerticalBenchmark("lekarz", 3, 2.5, 35, 2.5, 3.5, 300, 1200),
    # e-commerce
    ("e-commerce", 1): VerticalBenchmark("e-commerce", 1, 1.2, 45, 2.0, 1.5, 1000, 3000),
    ("e-commerce", 2): VerticalBenchmark("e-commerce", 2, 1.0, 38, 1.9, 1.5, 700, 2200),
    ("e-commerce", 3): VerticalBenchmark("e-commerce", 3, 0.8, 30, 1.8, 1.5, 500, 1500),
    # nieruchomości
    ("nieruchomości", 1): VerticalBenchmark("nieruchomości", 1, 9.0, 300, 2.0, 1.0, 2000, 7000),
    ("nieruchomości", 2): VerticalBenchmark("nieruchomości", 2, 6.0, 220, 1.9, 1.0, 1500, 5000),
    ("nieruchomości", 3): VerticalBenchmark("nieruchomości", 3, 4.0, 150, 1.7, 1.0, 1000, 3500),
    # edukacja
    ("edukacja", 1): VerticalBenchmark("edukacja", 1, 3.5, 60, 3.5, 3.0, 600, 2000),
    ("edukacja", 2): VerticalBenchmark("edukacja", 2, 2.5, 45, 3.3, 3.0, 400, 1400),
    ("edukacja", 3): VerticalBenchmark("edukacja", 3, 1.8, 30, 3.0, 3.0, 250, 900),
    # usługi domowe
    ("usługi domowe", 1): VerticalBenchmark("usługi domowe", 1, 4.0, 50, 3.8, 4.5, 500, 1600),
    ("usługi domowe", 2): VerticalBenchmark("usługi domowe", 2, 2.8, 38, 3.6, 4.5, 350, 1100),
    ("usługi domowe", 3): VerticalBenchmark("usługi domowe", 3, 1.8, 25, 3.3, 4.5, 200, 700),
}


def get_benchmark(vertical: str, city: str) -> VerticalBenchmark | None:
    """Return benchmark for a vertical + city. Returns None if vertical unknown."""
    tier = classify_city(city)
    return BENCHMARKS.get((vertical.lower(), tier))


def get_benchmark_by_tier(vertical: str, tier: int = 2) -> VerticalBenchmark | None:
    """Return benchmark for a vertical at a known city tier (default tier 2 = regional).

    Used when the vertical is known but the city is not (e.g. the free audit infers
    the vertical from account text but has no geo) — tier 2 is the conservative
    national-average choice.
    """
    return BENCHMARKS.get((vertical.lower(), tier))
