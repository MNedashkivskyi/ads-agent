from __future__ import annotations

from adcopilot.domain.evidence_grading import grade_comparison


def test_causal_when_backed_by_experiment() -> None:
    g = grade_comparison(
        baseline_conversions=10,
        baseline_impressions=1000,
        current_conversions=20,
        current_impressions=1000,
        has_causal_experiment=True,
    )
    assert g.grade == "CAUSAL"
    assert g.is_causal is True


def test_significant_observational() -> None:
    g = grade_comparison(
        baseline_conversions=40,
        baseline_impressions=5000,
        current_conversions=160,
        current_impressions=5000,
    )
    assert g.grade == "OBSERVATIONAL_SIGNIFICANT"
    assert g.is_causal is False
    assert g.p_value is not None and g.p_value < 0.05


def test_non_significant_observational() -> None:
    g = grade_comparison(
        baseline_conversions=10,
        baseline_impressions=1000,
        current_conversions=11,
        current_impressions=1000,
    )
    assert g.grade == "OBSERVATIONAL"
    assert "przyczynow" in g.caveat_pl.lower()


def test_underpowered_defaults_observational() -> None:
    g = grade_comparison(
        baseline_conversions=0,
        baseline_impressions=0,
        current_conversions=0,
        current_impressions=0,
    )
    assert g.grade == "OBSERVATIONAL"
    assert g.p_value is None
