"""Tests for actuals-vs-target comparison (Tier-3 Phase 2)."""

from __future__ import annotations

from adcopilot.domain.performance_targets import compare_to_targets


def test_none_when_no_targets():
    assert compare_to_targets(50.0, 3.0, target_cpa=None, target_roas=None) is None


def test_cpa_above_target_off_track():
    c = compare_to_targets(60.0, None, target_cpa=50.0, target_roas=None)
    assert c is not None
    assert c.cpa_vs_target_pct == 20.0  # 20% over target CPA
    assert c.on_track is False


def test_cpa_at_target_on_track():
    c = compare_to_targets(50.0, None, target_cpa=50.0, target_roas=None)
    assert c.cpa_vs_target_pct == 0.0
    assert c.on_track is True


def test_cpa_within_tolerance_on_track():
    # 8% over target, default tolerance 10% → still on track.
    c = compare_to_targets(54.0, None, target_cpa=50.0, target_roas=None)
    assert c.on_track is True


def test_roas_below_target_off_track():
    c = compare_to_targets(None, 3.0, target_cpa=None, target_roas=4.0)
    assert c.roas_vs_target_pct == -25.0  # 25% below target ROAS
    assert c.on_track is False


def test_roas_above_target_on_track():
    c = compare_to_targets(None, 5.0, target_cpa=None, target_roas=4.0)
    assert c.roas_vs_target_pct == 25.0
    assert c.on_track is True


def test_both_targets_must_be_met():
    # CPA good, ROAS bad → off track overall.
    c = compare_to_targets(40.0, 2.0, target_cpa=50.0, target_roas=4.0)
    assert c.cpa_vs_target_pct < 0
    assert c.roas_vs_target_pct < 0
    assert c.on_track is False


def test_missing_actual_skips_that_dimension():
    # Target set but actual unknown → that dimension is None and doesn't block.
    c = compare_to_targets(None, 5.0, target_cpa=50.0, target_roas=4.0)
    assert c.cpa_vs_target_pct is None
    assert c.roas_vs_target_pct == 25.0
    assert c.on_track is True


def test_as_dict_shape():
    c = compare_to_targets(60.0, 5.0, target_cpa=50.0, target_roas=4.0)
    d = c.as_dict()
    assert set(d) == {"cpa_vs_target_pct", "roas_vs_target_pct", "on_track"}
