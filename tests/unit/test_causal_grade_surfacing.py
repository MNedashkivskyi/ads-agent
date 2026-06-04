"""Tests that concluded experiments surface a CAUSAL evidence grade."""

from __future__ import annotations

from types import SimpleNamespace

from adcopilot.domain.campaign_experiment import ExperimentVerdict
from adcopilot.interfaces.api.causal_experiments import _causal_grade_for


def _exp(verdict: ExperimentVerdict) -> SimpleNamespace:
    return SimpleNamespace(
        verdict=verdict,
        control_metrics={"conversions": 40.0, "impressions": 5000},
        treatment_metrics={"conversions": 60.0, "impressions": 5100},
    )


def test_win_is_causal():
    grade = _causal_grade_for(_exp(ExperimentVerdict.WIN))
    assert grade is not None
    assert grade.grade == "CAUSAL"
    assert grade.caveat_pl  # Polish caveat present


def test_loss_is_causal():
    grade = _causal_grade_for(_exp(ExperimentVerdict.LOSS))
    assert grade is not None
    assert grade.is_causal


def test_pending_has_no_grade():
    assert _causal_grade_for(_exp(ExperimentVerdict.PENDING)) is None


def test_inconclusive_has_no_grade():
    assert _causal_grade_for(_exp(ExperimentVerdict.INCONCLUSIVE)) is None
