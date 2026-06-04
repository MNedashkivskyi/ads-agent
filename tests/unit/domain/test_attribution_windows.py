"""Unit tests for per-vertical attribution windows and the lag guard."""

from __future__ import annotations

from datetime import date

from adcopilot.application.detection.lag_guard import (
    COMPARISON_GAP_DAYS,
    conversions_settled,
    is_comparison_reliable,
)
from adcopilot.domain.polish_market.attribution_windows import (
    DEFAULT_WINDOW_DAYS,
    attribution_window_days,
)

# --------------------------------------------------------------------------- #
# attribution_window_days
# --------------------------------------------------------------------------- #


def test_unknown_vertical_uses_default():
    assert attribution_window_days("not-a-vertical") == DEFAULT_WINDOW_DAYS


def test_none_vertical_uses_default():
    assert attribution_window_days(None) == DEFAULT_WINDOW_DAYS


def test_fast_cycle_vertical_short_window():
    assert attribution_window_days("restauracja") <= COMPARISON_GAP_DAYS
    assert attribution_window_days("salon") <= COMPARISON_GAP_DAYS


def test_long_cycle_vertical_long_window():
    assert attribution_window_days("prawnik") > COMPARISON_GAP_DAYS
    assert attribution_window_days("nieruchomosci") > COMPARISON_GAP_DAYS


def test_case_insensitive():
    assert attribution_window_days("PRAWNIK") == attribution_window_days("prawnik")


# --------------------------------------------------------------------------- #
# is_comparison_reliable
# --------------------------------------------------------------------------- #


def test_reliable_when_window_within_gap():
    assert is_comparison_reliable(7) is True
    assert is_comparison_reliable(3) is True


def test_unreliable_when_window_exceeds_gap():
    assert is_comparison_reliable(45) is False
    assert is_comparison_reliable(8) is False


# --------------------------------------------------------------------------- #
# conversions_settled (historical-window helper)
# --------------------------------------------------------------------------- #


def test_conversions_settled_true_after_window():
    snap = date(2026, 1, 1)
    assert conversions_settled(snap, 14, today=date(2026, 1, 20)) is True


def test_conversions_settled_false_within_window():
    snap = date(2026, 1, 1)
    assert conversions_settled(snap, 14, today=date(2026, 1, 10)) is False
