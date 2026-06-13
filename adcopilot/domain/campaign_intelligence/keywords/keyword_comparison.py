"""keyword_comparison — the brand-vs-intent proof view (pure).

Scores validated candidates, groups them by intent-type, and produces the
side-by-side comparison the user sees: proof that brand keywords are nearly dead
while intent/problem keywords carry the volume that converts. Pure domain — no
I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from adcopilot.domain.campaign_intelligence.keywords import keyword_scorer
from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import (
    KeywordCandidate,
    KeywordStatus,
)
from adcopilot.domain.campaign_intelligence.keywords.value_objects import KeywordIntent
from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    DimensionPerformance,
)

_TOP_N = 8


@dataclass(frozen=True)
class RankedKeyword:
    phrase: str
    intent: str
    monthly_searches: int
    score: float
    competition: str


@dataclass(frozen=True)
class IntentGroup:
    intent: str
    keyword_count: int
    total_monthly_volume: int
    avg_score: float
    top_keywords: list[RankedKeyword] = field(default_factory=list)
    rationale: str = ""  # "Why this?" — the dimension's vertical track record


@dataclass(frozen=True)
class KeywordComparison:
    groups: list[IntentGroup]
    brand_total_volume: int
    intent_total_volume: int  # INTENT + PROBLEM combined
    verdict: str
    multiplier: float  # intent_total / max(brand_total, 1)


def build_comparison(
    candidates: list[KeywordCandidate],
    *,
    learned_weights: dict[str, float] | None = None,
    performance: dict[str, DimensionPerformance] | None = None,
) -> KeywordComparison:
    """Build the brand-vs-intent comparison from validated candidates.

    When ``performance`` (learned per-vertical metrics) is supplied, each group
    gets a "Why this?" rationale citing its track record in the vertical.
    """
    validated = [c for c in candidates if c.status is KeywordStatus.VALIDATED and c.volume]
    for c in validated:
        keyword_scorer.score_candidate(c, learned_weights)

    groups: list[IntentGroup] = []
    by_intent: dict[KeywordIntent, list[KeywordCandidate]] = {i: [] for i in KeywordIntent}
    for c in validated:
        by_intent[c.intent].append(c)

    for intent in KeywordIntent:
        members = by_intent[intent]
        total_volume = sum(c.volume.monthly_searches for c in members if c.volume)
        scores = [c.score.value for c in members if c.score]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        ranked = sorted(
            (
                RankedKeyword(
                    phrase=c.phrase,
                    intent=intent.value,
                    monthly_searches=c.volume.monthly_searches if c.volume else 0,
                    score=round(c.score.value, 4) if c.score else 0.0,
                    competition=c.volume.competition if c.volume else "UNKNOWN",
                )
                for c in members
            ),
            key=lambda r: (r.score, r.monthly_searches),
            reverse=True,
        )
        groups.append(
            IntentGroup(
                intent=intent.value,
                keyword_count=len(members),
                total_monthly_volume=total_volume,
                avg_score=round(avg_score, 4),
                top_keywords=ranked[:_TOP_N],
                rationale=_rationale(intent, performance),
            )
        )

    brand_total = next((g.total_monthly_volume for g in groups if g.intent == "BRAND"), 0)
    intent_total = sum(
        g.total_monthly_volume for g in groups if g.intent in ("INTENT", "PROBLEM")
    )
    multiplier = intent_total / max(brand_total, 1)
    return KeywordComparison(
        groups=groups,
        brand_total_volume=brand_total,
        intent_total_volume=intent_total,
        verdict=_verdict(brand_total, intent_total, multiplier),
        multiplier=round(multiplier, 1),
    )


def _rationale(
    intent: KeywordIntent, performance: dict[str, DimensionPerformance] | None
) -> str:
    """The 'Why this?' line: this intent-type's track record in the vertical."""
    if not performance:
        return ""
    perf = performance.get(intent.value)
    if perf is None or not perf.is_trusted:
        return ""
    return (
        f"Typ '{intent.value}' ma historię w tej branży: "
        f"{perf.sample_size:,} wyświetleń, {perf.weighted_conv:.1%} konwersji."
    ).replace(",", " ")


def _verdict(brand_total: int, intent_total: int, multiplier: float) -> str:
    """Human-readable Polish verdict for the comparison view."""
    if intent_total == 0 and brand_total == 0:
        return "Brak danych o wolumenie — wygeneruj i zwaliduj słowa kluczowe."
    if brand_total == 0:
        return (
            f"Słowa kluczowe oparte na intencji i problemie klienta mają "
            f"{intent_total:,} wyszukiwań miesięcznie. Słowa markowe nie mają "
            f"praktycznie żadnego wolumenu — klient szuka problemu, nie marki."
        ).replace(",", " ")
    if multiplier >= 2:
        return (
            f"Słowa oparte na intencji/problemie mają ~{multiplier:.0f}× większy "
            f"wolumen ({intent_total:,} vs {brand_total:,} wyszukiwań/mies.). "
            f"To dowód: klient szuka swojego problemu, nie nazwy marki."
        ).replace(",", " ")
    return (
        f"Wolumen intencji/problemu: {intent_total:,}, marki: {brand_total:,} "
        f"wyszukiwań miesięcznie."
    ).replace(",", " ")
