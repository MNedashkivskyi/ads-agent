"""Tests for Polish negative keyword intelligence."""

from __future__ import annotations

import pytest

from adcopilot.domain.launch.templates import _TEMPLATES
from adcopilot.domain.polish_market.negative_keywords import (
    POLISH_STANDARD_NEGATIVES,
    VERTICAL_NEGATIVES_PL,
)

REQUIRED_STANDARD_CATEGORIES = {
    "darmowy", "praca", "diy", "edukacja", "forum/media", "pobieranie",
}
REQUIRED_VERTICALS = {
    "salon", "prawnik", "restauracja", "lekarz", "ecommerce",
    "nieruchomości", "edukacja", "usługi domowe",
}


def test_standard_negatives_has_all_required_categories() -> None:
    labels = {label for label, _ in POLISH_STANDARD_NEGATIVES}
    assert labels == REQUIRED_STANDARD_CATEGORIES


def test_standard_negatives_each_category_has_min_terms() -> None:
    for label, terms in POLISH_STANDARD_NEGATIVES:
        assert len(terms) >= 5, f"Category '{label}' has fewer than 5 terms"


def test_vertical_negatives_has_all_required_verticals() -> None:
    assert set(VERTICAL_NEGATIVES_PL.keys()) >= REQUIRED_VERTICALS


@pytest.mark.parametrize("vertical", list(VERTICAL_NEGATIVES_PL.keys()))
def test_each_vertical_has_min_negatives(vertical: str) -> None:
    assert len(VERTICAL_NEGATIVES_PL[vertical]) >= 5, (
        f"Vertical '{vertical}' has fewer than 5 negative keywords"
    )


@pytest.mark.parametrize("vertical,template", list(_TEMPLATES.items()))
def test_templates_include_polish_negatives(vertical: str, template) -> None:
    negs_lower = [n.lower() for n in template.negatives]
    polish_standard_terms = [t for _, terms in POLISH_STANDARD_NEGATIVES for t in terms]
    has_polish = any(
        any(t in neg for t in polish_standard_terms)
        for neg in negs_lower
    )
    assert has_polish, f"Template '{vertical}' has no Polish standard negatives"
