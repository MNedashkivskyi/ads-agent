"""Conversion-lag guard for week-over-week detection rules.

The trend rules compare the latest snapshot against one ~7 days earlier. For a
vertical whose conversions keep landing for *longer* than that gap (law, real
estate), the latest window is badly undercounted, so a measured CPA spike or
conversion-rate drop is an artefact of attribution lag — not a real problem.

Detection runs *on* the snapshot date, so we can't simply "wait for conversions
to settle" within this comparison. Instead we judge whether the comparison is
trustworthy at all: it is reliable only when the vertical's attribution window
fits inside the comparison gap. When it doesn't, conversion-based alerts are
downgraded to advisory (and annotated) instead of firing as hard actions.
"""

from __future__ import annotations

from datetime import date

# The trend rules compare against a snapshot this many days old
# (mirrors ``run_detection._TREND_LOOKBACK_DAYS``).
COMPARISON_GAP_DAYS = 7


def is_comparison_reliable(
    attribution_window_days: int,
    comparison_gap_days: int = COMPARISON_GAP_DAYS,
) -> bool:
    """True when a week-over-week conversion comparison can be trusted.

    Reliable only when conversions settle within the comparison gap; for longer
    windows the latest window is undercounted and the comparison is an artefact.
    """
    return attribution_window_days <= comparison_gap_days


def conversions_settled(
    snapshot_date: date,
    attribution_window_days: int,
    today: date,
) -> bool:
    """True when conversions for ``snapshot_date`` have had time to land.

    Pure (``today`` passed explicitly). Used by callers that compare two
    *historical* windows and can therefore wait for settling, rather than the
    on-snapshot trend rules.
    """
    return (today - snapshot_date).days >= attribution_window_days
