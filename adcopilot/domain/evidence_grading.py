"""Evidence grading for performance claims (causal-measurement honesty layer).

Before/after comparisons (`PerformanceComparison`) are **observational**: auctions,
seasonality and Smart-Bidding learning move metrics on their own, so a metric moving
after a change does not prove the change caused it. This module grades a claim so the
product never presents correlation as proof:

- OBSERVATIONAL            — a before/after delta, not statistically distinguishable
- OBSERVATIONAL_SIGNIFICANT — delta is statistically significant but still confounded
- CAUSAL                   — backed by a native Google Ads experiment (control arm)

The significance test is the same two-proportion z-test used for experiments.
"""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.application.use_cases.evaluate_experiment import _two_proportion_z_test

DEFAULT_CONFIDENCE = 0.95


@dataclass(frozen=True)
class EvidenceGrade:
    grade: str  # OBSERVATIONAL | OBSERVATIONAL_SIGNIFICANT | CAUSAL
    p_value: float | None
    label_pl: str
    caveat_pl: str

    @property
    def is_causal(self) -> bool:
        return self.grade == "CAUSAL"


_CAUSAL = EvidenceGrade(
    grade="CAUSAL",
    p_value=None,
    label_pl="wynik przyczynowy (eksperyment z grupą kontrolną)",
    caveat_pl="Zmierzone w natywnym eksperymencie Google Ads — różnica wynika ze zmiany, nie z sezonowości.",
)


def grade_comparison(
    *,
    baseline_conversions: float,
    baseline_impressions: float,
    current_conversions: float,
    current_impressions: float,
    has_causal_experiment: bool = False,
    confidence_threshold: float = DEFAULT_CONFIDENCE,
) -> EvidenceGrade:
    """Grade a before/after comparison. CAUSAL only when a real experiment backs it."""
    if has_causal_experiment:
        return _CAUSAL

    p_value = _two_proportion_z_test(
        baseline_conversions, baseline_impressions, current_conversions, current_impressions
    )
    alpha = 1 - confidence_threshold
    significant = p_value is not None and p_value < alpha

    if significant:
        return EvidenceGrade(
            grade="OBSERVATIONAL_SIGNIFICANT",
            p_value=p_value,
            label_pl="zmiana obserwacyjna (istotna statystycznie)",
            caveat_pl=(
                "Różnica jest istotna statystycznie, ale to porównanie przed/po — "
                "nie dowodzi przyczynowości (możliwy wpływ sezonowości i aukcji). "
                "Aby potwierdzić, uruchom eksperyment."
            ),
        )
    return EvidenceGrade(
        grade="OBSERVATIONAL",
        p_value=p_value,
        label_pl="zmiana obserwacyjna (nieistotna statystycznie)",
        caveat_pl=(
            "To porównanie przed/po, nie dowód przyczynowości. Różnica nie jest "
            "istotna statystycznie. Aby zmierzyć rzeczywisty wpływ, uruchom eksperyment."
        ),
    )
