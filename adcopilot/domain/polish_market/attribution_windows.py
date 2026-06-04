"""Per-vertical conversion-attribution windows for the Polish market.

Week-over-week detection rules (CPA spike, CTR decline, conversion-rate drop)
compare a recent window against a 7-day-ago window. For verticals with long
sales cycles (law, real estate) conversions keep landing for weeks after the
click, so a naive comparison fires false "CPA spiked — pause!" alerts. This
module returns how many days conversions need to settle before a comparison is
trustworthy, keyed by vertical.

Keys mirror :mod:`adcopilot.domain.polish_market.seasonality` (``salon``,
``restauracja``, ``prawnik``, ``lekarz``, ``edukacja``) plus a few common
launch verticals; unknown verticals fall back to :data:`DEFAULT_WINDOW_DAYS`.
"""

from __future__ import annotations

# Default when the vertical is unknown. Deliberately set to the week-over-week
# comparison gap (7 days) so unknown-vertical accounts behave exactly as before
# — i.e. we do NOT suppress actionable CPA/CVR alerts on a guess. Only verticals
# we *know* are long-cycle (law, real estate, education, medical) relax the rule.
DEFAULT_WINDOW_DAYS = 7

# Vertical → days conversions take to substantially settle after the click.
_WINDOWS: dict[str, int] = {
    # Fast cycle — purchase/booking happens same session or within a few days.
    "salon": 7,
    "restauracja": 3,
    "fitness": 7,
    "ecommerce": 7,
    "sklep": 7,
    # Medium cycle — consideration over a couple of weeks.
    "lekarz": 14,
    "dentysta": 14,
    "fizjoterapia": 14,
    "edukacja": 21,
    # Long cycle — quotes, multiple touchpoints, weeks-to-months.
    "prawnik": 45,
    "nieruchomosci": 60,
    "b2b": 45,
    "budowlanka": 30,
}


def attribution_window_days(vertical: str | None) -> int:
    """Return the conversion-settling window (days) for a vertical.

    Falls back to :data:`DEFAULT_WINDOW_DAYS` for ``None`` or unknown verticals.
    """
    if not vertical:
        return DEFAULT_WINDOW_DAYS
    return _WINDOWS.get(vertical.strip().lower(), DEFAULT_WINDOW_DAYS)
