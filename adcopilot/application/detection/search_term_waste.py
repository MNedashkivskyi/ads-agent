"""Single source of truth for "is this search term wasteful?" (ADW-007).

Two detectors look at wasteful search terms through complementary lenses:

1. **Per-term, actionable (canonical for *actions*)** — the nightly engine rule
   ``WastedSearchTermRule`` (rule_01). It flags a specific term in a specific
   ad group as an ``ADD_NEGATIVE_KEYWORD`` recommendation when the term has
   real traffic (``clicks >= MIN_CLICKS``), zero conversions, and cost above a
   waste floor anchored to the account's acceptable CPA — with junk-intent
   signal words as a booster (see :func:`is_wasteful_term`).

2. **Account-level "budget hog" alarm** — the ``detect_search_term_waste`` use
   case. It surfaces any term that ate a large *share* of total daily spend
   (``> WASTE_SPEND_SHARE``) with zero conversions, regardless of wording. This
   is a louder, coarser signal used by the search-terms API list.

These two lenses answer different questions and are intentionally distinct.
What they must **never** disagree on is the junk-intent *vocabulary* — that
lives here, in :data:`WASTE_SIGNALS`, and both detectors import it via
:func:`has_waste_signal`. Keeping the vocabulary in one place is the
reconciliation: extend the list once and both the engine and the API agree.

The product serves the Polish market, so the vocabulary is Polish-first with
English kept for mixed-language accounts.
"""

from __future__ import annotations

# Minimum clicks before a zero-conversion term is considered to have "real"
# traffic worth acting on (used by the per-term actionable lens).
MIN_CLICKS = 5

# A term consuming more than this share of total daily spend with zero
# conversions is a budget hog (used by the account-level alarm lens).
WASTE_SPEND_SHARE = 0.20

# Junk-intent signal words/phrases. Matched as a case-insensitive substring,
# so multi-word phrases are fine. Conservative and extendable — add a term here
# and both detectors pick it up.
WASTE_SIGNALS: list[str] = [
    # Polish — "free / for free"
    "darmowy",
    "darmowe",
    "darmowa",
    "darmo",
    "za darmo",
    "bezpłatny",
    "bezpłatne",
    "gratis",
    # Polish — job seekers (not customers)
    "praca",
    "oferty pracy",
    "zarobki",
    "wynagrodzenie",
    "pensja",
    # Polish — research / how-to / informational intent
    "jak zrobić",
    "jak działa",
    "instrukcja",
    "przepis",
    "definicja",
    "co to jest",
    "opinie",
    "forum",
    "wzór",
    # English — kept for mixed-language accounts
    "free",
    "jobs",
    "salary",
    "how to",
    "diy",
    "wikipedia",
    "youtube",
]


def has_waste_signal(term: str) -> bool:
    """True if the search term contains any junk-intent signal word/phrase."""
    term_lower = term.lower()
    return any(signal in term_lower for signal in WASTE_SIGNALS)


def is_wasteful_term(
    *,
    term: str,
    clicks: int,
    conversions: float,
    cost_micros: int,
    cost_floor_micros: float,
    egregious_micros: float,
    min_clicks: int = MIN_CLICKS,
) -> bool:
    """Canonical per-term waste predicate (the actionable lens).

    A term is wasteful when it has real traffic (``clicks >= min_clicks``) and
    zero conversions and cost above ``cost_floor_micros``, AND either it
    contains a junk-intent signal word or its cost is egregious (greater than
    ``egregious_micros`` — e.g. more than one full acceptable conversion cost
    spent with nothing to show for it). Signal words are a booster, not a hard
    gate.
    """
    if clicks < min_clicks:
        return False
    if conversions != 0:
        return False
    if cost_micros <= cost_floor_micros:
        return False
    return has_waste_signal(term) or cost_micros > egregious_micros
