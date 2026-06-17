"""Pure waste-calculation engine for the free audit (Audit Funnel Phase 1).

Given an ``AuditDataset`` (the data the scan worker pulls read-only — Phase 2),
this computes a conservative, evidence-backed monthly *waste* figure and the
findings behind it, exactly per §3 of the audit-funnel plan. It is deliberately
free of I/O so it can be exhaustively unit-tested with synthetic datasets
(golden cases, T1.9).

Confidence tiers:
- Tier 1 (CONFIRMED) — money provably spent for zero return; feeds the headline.
- Tier 2 (ESTIMATED) — likely overpayment (low Quality Score); shown, never in
  the headline.
- Tier 3 (QUALITATIVE) — measurement gap / other issues; no PLN value.

Credibility guardrails (T1.7): a statistical-significance click threshold, an
"acceptable CPA" cost anchor from the Polish benchmark (no benchmark → only
junk-intent terms count, never a fabricated figure), dedup of keyword vs
search-term spend, conservative floor-to-10-PLN rounding, and a LIMITED
confidence state when there is too little data to stand behind a number.

The junk-intent vocabulary and the per-term waste predicate are reused from the
nightly engine (``detection.search_term_waste``) so the audit and the in-product
recommendations never disagree on what "wasteful" means.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from adcopilot.application.detection.search_term_waste import (
    MIN_CLICKS,
    has_waste_signal,
    is_wasteful_term,
)
from adcopilot.domain.audit import FindingTier, ReportConfidence, WasteCategory
from adcopilot.domain.polish_market.cpc_benchmarks import get_benchmark

_MICROS = 1_000_000
_FLOOR_UNIT_MICROS = 10 * _MICROS  # round the headline DOWN to the nearest 10 PLN


# ---------------------------------------------------------------------------
# Input contract — what the scan worker assembles (Phase 2) and feeds the engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchTermRow:
    term: str
    clicks: int
    conversions: float
    cost_micros: int
    matched_keyword: str | None = None  # for keyword/term dedup


@dataclass(frozen=True)
class KeywordRow:
    text: str
    clicks: int
    conversions: float
    cost_micros: int
    quality_score: int | None = None
    avg_cpc_micros: int = 0


@dataclass(frozen=True)
class AuditDataset:
    window_start: date
    window_end: date
    total_spend_micros: int
    search_terms: list[SearchTermRow] = field(default_factory=list)
    keywords: list[KeywordRow] = field(default_factory=list)
    vertical: str | None = None
    city: str | None = None
    # Pre-computed upstream (conversion-tracking audit + detection rules, Phase 2).
    measurement_gap_pct: float = 0.0
    issues_count: int = 0
    days_of_data: int = 30


@dataclass(frozen=True)
class WasteConfig:
    min_days: int = 30
    min_total_spend_micros: int = (
        50 * _MICROS
    )  # below ~50 PLN/window we can't stand behind a number
    keyword_min_clicks: int = 8
    min_terms_for_high_confidence: int = 20


DEFAULT_CONFIG = WasteConfig()


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FindingSpec:
    category: WasteCategory
    tier: FindingTier
    title: str
    severity: str
    amount_micros: int | None
    evidence: dict[str, object]


@dataclass(frozen=True)
class WasteComputation:
    window_start: date
    window_end: date
    total_spend_micros: int
    headline_waste_micros: int
    measurement_gap_pct: float
    confidence: ReportConfidence
    findings: list[FindingSpec]

    @property
    def annual_waste_micros(self) -> int:
        return self.headline_waste_micros * 12


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def _severity(amount_micros: int, total_spend_micros: int) -> str:
    if total_spend_micros > 0 and amount_micros >= 0.10 * total_spend_micros:
        return "HIGH"
    return "MEDIUM"


def _floor_to_10_pln(micros: int) -> int:
    if micros <= 0:
        return 0
    return (micros // _FLOOR_UNIT_MICROS) * _FLOOR_UNIT_MICROS


def _term_examples(rows: list[SearchTermRow], limit: int = 5) -> list[dict[str, object]]:
    top = sorted(rows, key=lambda r: r.cost_micros, reverse=True)[:limit]
    return [{"term": r.term, "clicks": r.clicks, "cost_micros": r.cost_micros} for r in top]


def _keyword_examples(rows: list[KeywordRow], limit: int = 5) -> list[dict[str, object]]:
    top = sorted(rows, key=lambda r: r.cost_micros, reverse=True)[:limit]
    return [{"keyword": r.text, "clicks": r.clicks, "cost_micros": r.cost_micros} for r in top]


def compute_waste(dataset: AuditDataset, config: WasteConfig = DEFAULT_CONFIG) -> WasteComputation:
    """Compute the waste report + findings for a dataset (pure, no I/O)."""
    benchmark = (
        get_benchmark(dataset.vertical, dataset.city) if dataset.vertical and dataset.city else None
    )
    # "Acceptable CPA" anchor. With a benchmark we can also flag egregious
    # zero-conversion spend; without one we stay conservative and count only
    # junk-intent terms (egregious threshold = infinity).
    acceptable_cpa_micros = int(round(benchmark.avg_cpa_pln * _MICROS)) if benchmark else None
    egregious_micros: float = (
        float(acceptable_cpa_micros) if acceptable_cpa_micros is not None else float("inf")
    )

    # --- Tier 1: confirmed waste from wasteful search terms -----------------
    wasteful_terms = [
        t
        for t in dataset.search_terms
        if is_wasteful_term(
            term=t.term,
            clicks=t.clicks,
            conversions=t.conversions,
            cost_micros=t.cost_micros,
            cost_floor_micros=0.0,
            egregious_micros=egregious_micros,
            min_clicks=MIN_CLICKS,
        )
    ]
    # Disjoint partition so the two categories never double-count: junk-intent
    # terms a negative keyword would block vs. egregious zero-conversion spend.
    negative_terms = [t for t in wasteful_terms if has_waste_signal(t.term)]
    egregious_terms = [t for t in wasteful_terms if not has_waste_signal(t.term)]
    w_negative = sum(t.cost_micros for t in negative_terms)
    w_searchterm = sum(t.cost_micros for t in egregious_terms)

    # --- Tier 1: confirmed waste from zero-conversion keywords --------------
    # Dedup: skip keywords whose spend is already counted via their search terms.
    counted_keywords = {t.matched_keyword for t in wasteful_terms if t.matched_keyword}
    wasteful_keywords = [
        k
        for k in dataset.keywords
        if k.clicks >= config.keyword_min_clicks
        and k.conversions == 0
        and k.cost_micros > egregious_micros
        and k.text not in counted_keywords
    ]
    w_keyword = sum(k.cost_micros for k in wasteful_keywords)

    raw_headline = w_searchterm + w_negative + w_keyword
    headline = min(_floor_to_10_pln(raw_headline), dataset.total_spend_micros)

    # --- Tier 2: estimated overpayment from low Quality Score ---------------
    w_qs = 0
    qs_keywords: list[KeywordRow] = []
    if benchmark is not None:
        bench_cpc_micros = benchmark.avg_cpc_pln * _MICROS
        for k in dataset.keywords:
            if k.quality_score is not None and k.quality_score <= 5 and k.conversions > 0:
                over = int(max(0.0, k.avg_cpc_micros - bench_cpc_micros) * k.clicks)
                if over > 0:
                    w_qs += over
                    qs_keywords.append(k)

    # --- Confidence ---------------------------------------------------------
    if (
        dataset.days_of_data < config.min_days
        or dataset.total_spend_micros < config.min_total_spend_micros
    ):
        confidence = ReportConfidence.LIMITED
    elif benchmark is None or len(dataset.search_terms) < config.min_terms_for_high_confidence:
        confidence = ReportConfidence.MEDIUM
    else:
        confidence = ReportConfidence.HIGH

    # --- Findings -----------------------------------------------------------
    findings: list[FindingSpec] = []
    if w_searchterm > 0:
        findings.append(
            FindingSpec(
                category=WasteCategory.SEARCHTERM_WASTE,
                tier=FindingTier.CONFIRMED,
                title="Zmarnowany budżet na frazy bez konwersji",
                severity=_severity(w_searchterm, dataset.total_spend_micros),
                amount_micros=w_searchterm,
                evidence={
                    "count": len(egregious_terms),
                    "examples": _term_examples(egregious_terms),
                },
            )
        )
    if w_negative > 0:
        findings.append(
            FindingSpec(
                category=WasteCategory.NEGATIVE_BLOCKABLE,
                tier=FindingTier.CONFIRMED,
                title="Frazy do zablokowania minus-słowami",
                severity=_severity(w_negative, dataset.total_spend_micros),
                amount_micros=w_negative,
                evidence={"count": len(negative_terms), "examples": _term_examples(negative_terms)},
            )
        )
    if w_keyword > 0:
        findings.append(
            FindingSpec(
                category=WasteCategory.KEYWORD_WASTE,
                tier=FindingTier.CONFIRMED,
                title="Słowa kluczowe bez konwersji",
                severity=_severity(w_keyword, dataset.total_spend_micros),
                amount_micros=w_keyword,
                evidence={
                    "count": len(wasteful_keywords),
                    "examples": _keyword_examples(wasteful_keywords),
                },
            )
        )
    if w_qs > 0:
        findings.append(
            FindingSpec(
                category=WasteCategory.QS_OVERPAYMENT,
                tier=FindingTier.ESTIMATED,
                title="Zawyżone CPC przy niskim Quality Score (szacunkowo)",
                severity=_severity(w_qs, dataset.total_spend_micros),
                amount_micros=w_qs,
                evidence={
                    "count": len(qs_keywords),
                    "examples": _keyword_examples(qs_keywords),
                },
            )
        )
    if dataset.measurement_gap_pct > 0:
        findings.append(
            FindingSpec(
                category=WasteCategory.MEASUREMENT_GAP,
                tier=FindingTier.QUALITATIVE,
                title="Luka w pomiarze konwersji",
                severity="HIGH" if dataset.measurement_gap_pct >= 0.3 else "MEDIUM",
                amount_micros=None,
                evidence={"measurement_gap_pct": dataset.measurement_gap_pct},
            )
        )
    if dataset.issues_count > 0:
        findings.append(
            FindingSpec(
                category=WasteCategory.ISSUE,
                tier=FindingTier.QUALITATIVE,
                title="Pozostałe wykryte problemy",
                severity="MEDIUM",
                amount_micros=None,
                evidence={"count": dataset.issues_count},
            )
        )

    return WasteComputation(
        window_start=dataset.window_start,
        window_end=dataset.window_end,
        total_spend_micros=dataset.total_spend_micros,
        headline_waste_micros=headline,
        measurement_gap_pct=dataset.measurement_gap_pct,
        confidence=confidence,
        findings=findings,
    )
