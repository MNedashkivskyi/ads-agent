"""Golden-case tests for the waste-calculation engine (Audit Funnel T1.9).

These lock the §3 contract: tier partitioning, the significance threshold, the
benchmark cost anchor, keyword/term dedup, conservative floor rounding, the
LIMITED-data state, and that estimated/qualitative findings never enter the
headline.
"""

from __future__ import annotations

from datetime import date

from adcopilot.application.audit.waste_engine import (
    AuditDataset,
    KeywordRow,
    SearchTermRow,
    WasteConfig,
    compute_waste,
)
from adcopilot.domain.audit import FindingTier, ReportConfidence, WasteCategory

_M = 1_000_000


def _ds(**kw: object) -> AuditDataset:
    base: dict[str, object] = dict(
        window_start=date(2026, 5, 1),
        window_end=date(2026, 5, 31),
        total_spend_micros=10_000 * _M,
        search_terms=[],
        keywords=[],
        vertical="e-commerce",
        city="Warszawa",
        days_of_data=30,
    )
    base.update(kw)
    return AuditDataset(**base)  # type: ignore[arg-type]


def _amount(comp, category: WasteCategory) -> int | None:
    for f in comp.findings:
        if f.category is category:
            return f.amount_micros
    return None


def test_heavy_waste_with_benchmark_partitions_and_sums() -> None:
    comp = compute_waste(
        _ds(
            search_terms=[
                SearchTermRow(
                    "kurs excel za darmo", clicks=20, conversions=0, cost_micros=200 * _M
                ),
                SearchTermRow(
                    "ekspresowa dostawa mebli", clicks=30, conversions=0, cost_micros=300 * _M
                ),
                SearchTermRow(
                    "kup buty", clicks=3, conversions=0, cost_micros=100 * _M
                ),  # below click floor
                SearchTermRow(
                    "sklep z butami", clicks=50, conversions=5, cost_micros=400 * _M
                ),  # converts
            ],
            keywords=[
                KeywordRow("meble ogrodowe", clicks=40, conversions=0, cost_micros=500 * _M),
                KeywordRow(
                    "stół drewniany",
                    clicks=100,
                    conversions=10,
                    cost_micros=900 * _M,
                    quality_score=3,
                    avg_cpc_micros=3 * _M,
                ),
            ],
        )
    )
    assert _amount(comp, WasteCategory.NEGATIVE_BLOCKABLE) == 200 * _M  # "za darmo" signal
    assert _amount(comp, WasteCategory.SEARCHTERM_WASTE) == 300 * _M  # egregious, no signal
    assert _amount(comp, WasteCategory.KEYWORD_WASTE) == 500 * _M
    # Headline = Tier-1 only; QS overpayment is excluded.
    assert comp.headline_waste_micros == 1000 * _M
    assert comp.annual_waste_micros == 12_000 * _M
    qs = next(f for f in comp.findings if f.category is WasteCategory.QS_OVERPAYMENT)
    assert qs.tier is FindingTier.ESTIMATED
    assert qs.amount_micros == 180 * _M  # (3.0 - 1.2) PLN * 100 clicks
    assert comp.confidence is ReportConfidence.MEDIUM  # 4 terms < high-confidence threshold


def test_clean_account_has_zero_headline() -> None:
    comp = compute_waste(
        _ds(
            search_terms=[
                SearchTermRow("sklep buty", clicks=80, conversions=8, cost_micros=400 * _M)
            ],
            keywords=[KeywordRow("buty", clicks=80, conversions=8, cost_micros=400 * _M)],
        )
    )
    assert comp.headline_waste_micros == 0
    assert all(f.amount_micros in (None, 0) for f in comp.findings)


def test_below_click_threshold_is_not_flagged() -> None:
    comp = compute_waste(
        _ds(
            search_terms=[
                SearchTermRow("za darmo coś", clicks=4, conversions=0, cost_micros=300 * _M)
            ]
        )
    )
    assert comp.headline_waste_micros == 0
    assert comp.findings == []


def test_no_benchmark_counts_only_junk_intent_terms() -> None:
    comp = compute_waste(
        _ds(
            vertical=None,
            city=None,
            search_terms=[
                SearchTermRow(
                    "praca zdalna", clicks=10, conversions=0, cost_micros=80 * _M
                ),  # signal
                SearchTermRow(
                    "duża dostawa", clicks=10, conversions=0, cost_micros=1000 * _M
                ),  # no signal
            ],
            keywords=[KeywordRow("x", clicks=20, conversions=0, cost_micros=2000 * _M)],
        )
    )
    assert _amount(comp, WasteCategory.NEGATIVE_BLOCKABLE) == 80 * _M
    assert _amount(comp, WasteCategory.SEARCHTERM_WASTE) is None  # egregious path off w/o benchmark
    assert _amount(comp, WasteCategory.KEYWORD_WASTE) is None
    assert comp.headline_waste_micros == 80 * _M


def test_keyword_term_dedup_prevents_double_counting() -> None:
    comp = compute_waste(
        _ds(
            search_terms=[
                SearchTermRow(
                    "tania dostawa ekspres",
                    clicks=10,
                    conversions=0,
                    cost_micros=200 * _M,
                    matched_keyword="dostawa",
                )
            ],
            keywords=[KeywordRow("dostawa", clicks=20, conversions=0, cost_micros=300 * _M)],
        )
    )
    assert _amount(comp, WasteCategory.SEARCHTERM_WASTE) == 200 * _M
    assert _amount(comp, WasteCategory.KEYWORD_WASTE) is None  # deduped out
    assert comp.headline_waste_micros == 200 * _M


def test_limited_data_yields_limited_confidence() -> None:
    short = compute_waste(_ds(days_of_data=10))
    assert short.confidence is ReportConfidence.LIMITED
    low_spend = compute_waste(_ds(total_spend_micros=10 * _M))
    assert low_spend.confidence is ReportConfidence.LIMITED


def test_qualitative_findings_have_no_amount_and_skip_headline() -> None:
    comp = compute_waste(_ds(measurement_gap_pct=0.6, issues_count=12))
    gap = next(f for f in comp.findings if f.category is WasteCategory.MEASUREMENT_GAP)
    issues = next(f for f in comp.findings if f.category is WasteCategory.ISSUE)
    assert (
        gap.tier is FindingTier.QUALITATIVE and gap.amount_micros is None and gap.severity == "HIGH"
    )
    assert issues.amount_micros is None
    assert comp.headline_waste_micros == 0


def test_headline_floored_down_to_nearest_10_pln() -> None:
    comp = compute_waste(
        _ds(
            search_terms=[
                SearchTermRow(
                    "ogromna dostawa premium", clicks=10, conversions=0, cost_micros=1_234_567_890
                )
            ]
        )
    )
    # 1_234_567_890 floored to the nearest 10 PLN (10_000_000 micros).
    assert comp.headline_waste_micros == 1_230 * _M


def test_high_confidence_requires_enough_terms() -> None:
    terms = [
        SearchTermRow(f"konwertująca fraza {i}", clicks=30, conversions=3, cost_micros=50 * _M)
        for i in range(25)
    ]
    comp = compute_waste(_ds(search_terms=terms), config=WasteConfig())
    assert comp.confidence is ReportConfidence.HIGH
