"""Keyword-track value objects: KeywordIntent, SearchVolume, KeywordScore."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# Minimum monthly searches for a keyword to be worth shipping. Below this a
# keyword adds noise and dilutes the ad group without bringing traffic.
MIN_VIABLE_VOLUME = 10

# The dimension name used to namespace keyword learning in dimension_performance.
KEYWORD_INTENT_DIMENSION = "keyword_intent"


class KeywordIntent(StrEnum):
    """The strategic dimension of the keyword track.

    The same disease as the hook problem — product-anchored generation — is cured
    by generating along the customer's *intent*:

    * ``BRAND`` — the customer already knows the product ("icoone Warszawa").
      Kept, but low-value when the brand is niche.
    * ``INTENT`` — the service/effect the customer searches without knowing the
      product ("drenaż limfatyczny", "modelowanie sylwetki").
    * ``PROBLEM`` — how the customer describes their pain ("nie mogę schudnąć z ud").
    """

    BRAND = "BRAND"
    INTENT = "INTENT"
    PROBLEM = "PROBLEM"

    # ``.value`` is provided by StrEnum and satisfies the StrategicDimension
    # protocol; we only add the dimension namespace and the static prior.

    @property
    def dimension_name(self) -> str:
        return KEYWORD_INTENT_DIMENSION

    @property
    def default_weight(self) -> float:
        """Static prior intent-weight, used before learned weights exist.

        PROBLEM/INTENT > BRAND: intent-anchored keywords carry the volume and
        convert; brand keywords are gray when the brand is niche. Replaced by
        learned weights in Phase 6.
        """
        return _DEFAULT_INTENT_WEIGHTS[self]


_DEFAULT_INTENT_WEIGHTS: dict[KeywordIntent, float] = {
    KeywordIntent.PROBLEM: 1.3,
    KeywordIntent.INTENT: 1.2,
    KeywordIntent.BRAND: 0.7,
}


# Competition → scoring multiplier. Lower competition is cheaper to win, so it is
# weighted up slightly; unknown is treated as neutral.
_COMPETITION_WEIGHTS: dict[str, float] = {
    "LOW": 1.1,
    "MEDIUM": 1.0,
    "HIGH": 0.85,
    "UNKNOWN": 1.0,
}


def competition_weight(competition: str) -> float:
    """Return the scoring multiplier for a competition level string."""
    return _COMPETITION_WEIGHTS.get(competition.upper(), 1.0)


@dataclass(frozen=True)
class SearchVolume:
    """Real demand for a phrase, from Keyword Planner or DataForSEO.

    ``is_bucketed`` is True when the source returned a range ("1K–10K") rather
    than an exact number — fresh client accounts do this, and it triggers the
    DataForSEO fallback. Bid bounds are in micros of the account currency.
    """

    monthly_searches: int
    competition: str = "UNKNOWN"
    cpc_low_micros: int = 0
    cpc_high_micros: int = 0
    is_bucketed: bool = False

    @property
    def is_viable(self) -> bool:
        """True when volume clears the minimum viability threshold."""
        return self.monthly_searches >= MIN_VIABLE_VOLUME

    def viable_at(self, threshold: int) -> bool:
        return self.monthly_searches >= threshold

    @property
    def competition_weight(self) -> float:
        return competition_weight(self.competition)


@dataclass(frozen=True, order=True)
class KeywordScore:
    """A keyword's computed rank score. Ordered so candidates sort by score."""

    value: float

    @classmethod
    def zero(cls) -> KeywordScore:
        return cls(0.0)
