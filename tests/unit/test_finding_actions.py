"""Unit tests for the audit finding → fix mapping (Audit Funnel T2.5 — pure)."""

from __future__ import annotations

from adcopilot.application.audit.finding_actions import fix_action_for
from adcopilot.domain.audit import WasteCategory
from adcopilot.domain.recommendation import RecommendationKind


def test_every_monetised_category_has_a_fix() -> None:
    # All categories except the generic ISSUE map to a concrete fix.
    for category in WasteCategory:
        fix = fix_action_for(category)
        if category is WasteCategory.ISSUE:
            assert fix is None
        else:
            assert fix is not None
            assert fix.label_pl.strip()  # non-empty Polish label


def test_search_term_waste_adds_negatives_and_is_actionable() -> None:
    fix = fix_action_for(WasteCategory.SEARCHTERM_WASTE)
    assert fix is not None
    assert fix.kind is RecommendationKind.ADD_NEGATIVE_KEYWORD
    assert fix.actionable is True


def test_keyword_waste_pauses_keywords() -> None:
    fix = fix_action_for(WasteCategory.KEYWORD_WASTE)
    assert fix is not None
    assert fix.kind is RecommendationKind.PAUSE_KEYWORD
    assert fix.actionable is True


def test_advisory_categories_are_not_one_click() -> None:
    # Quality-score and measurement fixes need human action — not auto-applied.
    for category in (WasteCategory.QS_OVERPAYMENT, WasteCategory.MEASUREMENT_GAP):
        fix = fix_action_for(category)
        assert fix is not None
        assert fix.actionable is False


def test_generic_issue_has_no_fix() -> None:
    assert fix_action_for(WasteCategory.ISSUE) is None
