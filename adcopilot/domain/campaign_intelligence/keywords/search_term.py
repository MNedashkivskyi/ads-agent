"""SearchTerm entity + harvester — discover keywords from reality (pure).

The killer feature. Google's search-term report shows the *actual queries people
typed* that triggered an ad — not your keywords, the real searches. This is the
icoone discovery automated: it surfaces that nobody typed "icoone" and everybody
typed "drenaż limfatyczny", and feeds those real converting terms back as new
keyword candidates. The same report yields negative-keyword candidates: terms
that burn spend with zero conversions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PROMOTE = "promote"
NEGATIVE = "negative"


@dataclass(frozen=True)
class SearchTerm:
    """One actual search query and its aggregated performance."""

    term: str
    matched_keyword: str
    impressions: int
    clicks: int
    conversions: float
    cost_micros: int
    intent: str | None = None  # attributed via the matched keyword, when known

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions > 0 else 0.0


@dataclass(frozen=True)
class SearchTermProposal:
    term: str
    kind: str  # PROMOTE | NEGATIVE
    impressions: int
    clicks: int
    conversions: float
    cost_micros: int
    ctr: float
    intent: str | None = None


@dataclass(frozen=True)
class HarvestResult:
    promotions: list[SearchTermProposal] = field(default_factory=list)
    negatives: list[SearchTermProposal] = field(default_factory=list)


# Default thresholds — conservative; tune from real data.
MIN_PROMOTE_CLICKS = 10
MIN_PROMOTE_CTR = 0.03
MIN_PROMOTE_CONVERSIONS = 1.0
NEGATIVE_MIN_SPEND_MICROS = 20_000_000  # ~20 currency units burned


def harvest(
    terms: list[SearchTerm],
    existing_keywords: set[str],
    *,
    min_clicks: int = MIN_PROMOTE_CLICKS,
    min_ctr: float = MIN_PROMOTE_CTR,
    min_conversions: float = MIN_PROMOTE_CONVERSIONS,
    negative_min_spend_micros: int = NEGATIVE_MIN_SPEND_MICROS,
) -> HarvestResult:
    """Promote real winning queries; flag wasteful ones as negatives.

    * **Promote** — a term not already a keyword that either converts
      (``conversions >= min_conversions``) or shows strong intent (enough clicks
      at a healthy CTR).
    * **Negative** — a term that burned real spend with zero conversions.

    Terms already present as keywords are never re-proposed.
    """
    existing = {k.strip().lower() for k in existing_keywords}
    promotions: list[SearchTermProposal] = []
    negatives: list[SearchTermProposal] = []
    seen_promote: set[str] = set()
    seen_negative: set[str] = set()

    for t in terms:
        key = t.term.strip().lower()
        if not key or key in existing:
            continue

        converts = t.conversions >= min_conversions
        strong_intent = t.clicks >= min_clicks and t.ctr >= min_ctr
        # Burning real spend with zero conversions is waste — this takes
        # precedence over "strong intent" (clicks that never convert are the
        # textbook negative-keyword candidate).
        wasteful = t.conversions == 0 and t.cost_micros >= negative_min_spend_micros

        if wasteful and not converts and key not in seen_negative:
            seen_negative.add(key)
            negatives.append(
                SearchTermProposal(
                    term=t.term,
                    kind=NEGATIVE,
                    impressions=t.impressions,
                    clicks=t.clicks,
                    conversions=t.conversions,
                    cost_micros=t.cost_micros,
                    ctr=t.ctr,
                    intent=t.intent,
                )
            )
        elif (converts or strong_intent) and key not in seen_promote:
            seen_promote.add(key)
            promotions.append(
                SearchTermProposal(
                    term=t.term,
                    kind=PROMOTE,
                    impressions=t.impressions,
                    clicks=t.clicks,
                    conversions=t.conversions,
                    cost_micros=t.cost_micros,
                    ctr=t.ctr,
                    intent=t.intent,
                )
            )

    return HarvestResult(promotions=promotions, negatives=negatives)
