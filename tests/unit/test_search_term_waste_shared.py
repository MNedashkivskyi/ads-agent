"""ADW-007: the two search-term-waste detectors share one junk vocabulary."""

from __future__ import annotations

from adcopilot.application.detection.search_term_waste import (
    WASTE_SIGNALS,
    has_waste_signal,
    is_wasteful_term,
)


def test_polish_and_english_signals_present() -> None:
    assert "darmowy" in WASTE_SIGNALS  # Polish
    assert "free" in WASTE_SIGNALS  # English


def test_has_waste_signal_is_case_insensitive() -> None:
    assert has_waste_signal("DARMOWY program")
    assert has_waste_signal("Free Trial")
    assert not has_waste_signal("kancelaria prawna warszawa")


def test_is_wasteful_term_requires_clicks_and_zero_conversions() -> None:
    base = dict(cost_floor_micros=3_000_000, egregious_micros=10_000_000)
    # below click floor
    assert not is_wasteful_term(term="darmowy", clicks=4, conversions=0, cost_micros=5_000_000, **base)
    # has a conversion
    assert not is_wasteful_term(term="darmowy", clicks=9, conversions=1, cost_micros=5_000_000, **base)
    # below cost floor
    assert not is_wasteful_term(term="darmowy", clicks=9, conversions=0, cost_micros=2_000_000, **base)
    # junk signal + above floor → wasteful
    assert is_wasteful_term(term="darmowy", clicks=9, conversions=0, cost_micros=5_000_000, **base)
    # no signal but egregious cost → wasteful
    assert is_wasteful_term(term="kancelaria", clicks=9, conversions=0, cost_micros=12_000_000, **base)
    # no signal, not egregious → not wasteful
    assert not is_wasteful_term(term="kancelaria", clicks=9, conversions=0, cost_micros=5_000_000, **base)


def test_engine_rule_and_use_case_agree_on_vocabulary() -> None:
    """rule_01 and the detect_search_term_waste use case must classify junk
    terms identically — they import the same has_waste_signal."""
    from adcopilot.application.detection.rules import rule_01_wasted_search_term as r1
    from adcopilot.application.use_cases import detect_search_term_waste as uc

    # Both modules reference the shared helper (same object).
    assert r1.is_wasteful_term is is_wasteful_term
    assert uc.has_waste_signal is has_waste_signal
