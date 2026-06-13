"""Phase 3 — creative VOs, policy screener, scorer, RSA assembly, selection."""

from __future__ import annotations

import pytest

from adcopilot.domain.campaign_intelligence.creatives import (
    angle_library,
    hook_scorer,
    hook_selection,
    policy_screener,
)
from adcopilot.domain.campaign_intelligence.creatives.ad_surface import AdSurface, char_limit
from adcopilot.domain.campaign_intelligence.creatives.angle import Angle
from adcopilot.domain.campaign_intelligence.creatives.hook_candidate import HookCandidate
from adcopilot.domain.campaign_intelligence.creatives.hook_set import HookSet
from adcopilot.domain.campaign_intelligence.creatives.policy_risk import PolicyRisk
from adcopilot.domain.campaign_intelligence.shared.strategic_dimension import StrategicDimension


# --- VOs --------------------------------------------------------------------


def test_surface_char_limits() -> None:
    assert char_limit(AdSurface.HEADLINE) == 30
    assert char_limit(AdSurface.DESCRIPTION) == 90


def test_angle_is_strategic_dimension() -> None:
    assert isinstance(Angle.PAIN, StrategicDimension)
    assert Angle.PAIN.dimension_name == "angle"


def test_angle_library_is_data_driven_and_complete() -> None:
    # Every angle has a spec; adding an angle is purely a data change.
    assert set(angle_library.ANGLE_LIBRARY) == set(Angle)
    assert len(angle_library.ANGLE_LIBRARY) == 7
    for spec in angle_library.ANGLE_LIBRARY.values():
        assert spec.eligible_surfaces  # at least one eligible surface


def test_over_limit_headline_rejected_at_construction() -> None:
    with pytest.raises(ValueError):
        HookCandidate(text="x" * 31, angle=Angle.PAIN, surface=AdSurface.HEADLINE)
    # 30 chars is fine.
    HookCandidate(text="x" * 30, angle=Angle.PAIN, surface=AdSurface.HEADLINE)


# --- Policy screener --------------------------------------------------------


def test_body_shaming_flagged_high() -> None:
    finding = policy_screener.screen("Masz grube uda? Zmień to")
    assert finding.risk is PolicyRisk.HIGH
    assert finding.reason


def test_medical_overclaim_flagged_high() -> None:
    finding = policy_screener.screen("Wyleczy cellulit w 100% skuteczności")
    assert finding.risk is PolicyRisk.HIGH
    assert finding.reason


def test_clean_hook_is_low_risk() -> None:
    finding = policy_screener.screen("Gładsza skóra w 4 tygodnie", Angle.SOCIAL_PROOF)
    assert finding.risk is PolicyRisk.LOW


# --- Scorer -----------------------------------------------------------------


def test_high_risk_penalised_not_dropped() -> None:
    low = hook_scorer.compute_score(judge=0.8, risk=PolicyRisk.LOW, angle=Angle.PAIN)
    high = hook_scorer.compute_score(judge=0.8, risk=PolicyRisk.HIGH, angle=Angle.PAIN)
    assert high.value < low.value  # penalised
    assert high.value > 0  # but not auto-dropped


def test_scorer_is_pure_and_deterministic() -> None:
    a = hook_scorer.compute_score(judge=0.7, risk=PolicyRisk.MEDIUM, angle=Angle.RESULT)
    b = hook_scorer.compute_score(judge=0.7, risk=PolicyRisk.MEDIUM, angle=Angle.RESULT)
    assert a == b


def test_learned_angle_prior_overrides_stub() -> None:
    s = hook_scorer.compute_score(
        judge=0.5, risk=PolicyRisk.LOW, angle=Angle.PAIN, learned_weights={"PAIN": 3.0}
    )
    assert s.angle_prior == 3.0


# --- Selection diversity ----------------------------------------------------


def _scored(text: str, angle: Angle, score: float) -> HookCandidate:
    c = HookCandidate(text=text, angle=angle, surface=AdSurface.HEADLINE)
    from adcopilot.domain.campaign_intelligence.creatives.hook_score import HookScore

    c.score = HookScore(score)
    return c


def test_selection_never_all_from_one_angle() -> None:
    # PAIN dominates on score, but selection must still include other angles.
    candidates = [
        _scored("p1", Angle.PAIN, 0.99),
        _scored("p2", Angle.PAIN, 0.98),
        _scored("p3", Angle.PAIN, 0.97),
        _scored("r1", Angle.RESULT, 0.50),
        _scored("o1", Angle.OBJECTION, 0.40),
    ]
    selected = hook_selection.select_for_surface(candidates, k=3)
    angles = {c.angle for c in selected}
    assert len(angles) > 1  # not all from PAIN
    assert selected[0].angle is Angle.PAIN  # but the strongest still leads


# --- RSA assembly + pinning -------------------------------------------------


def test_rsa_assembly_pins_top_headline_and_tags_angle() -> None:
    headlines = [_scored(f"Nagłówek {i}", Angle.PAIN if i == 0 else Angle.RESULT, 0.9 - i * 0.1)
                 for i in range(3)]
    descriptions = [
        HookCandidate(text=f"Opis numer {i} który konwertuje", angle=Angle.RESULT,
                      surface=AdSurface.DESCRIPTION)
        for i in range(2)
    ]
    hook_set = HookSet(headlines + descriptions)
    assert hook_set.is_valid_rsa()
    top = hook_set.pin_top_headline()
    assert top is not None and top.pinned_slot == "HEADLINE_1"
    payload = hook_set.to_rsa_payload()
    assert len(payload["headlines"]) == 3
    assert len(payload["descriptions"]) == 2
    # Every asset carries its angle (the Phase 4 attribution gate).
    assert all("angle" in a for a in payload["headlines"])
    assert any(a.get("pinned_field") == "HEADLINE_1" for a in payload["headlines"])


def test_rsa_validate_rejects_incomplete_set() -> None:
    hook_set = HookSet([_scored("only one", Angle.PAIN, 0.5)])
    assert not hook_set.is_valid_rsa()
    with pytest.raises(ValueError):
        hook_set.to_rsa_payload()
