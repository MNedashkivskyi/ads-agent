"""Unit tests for audience signal wiring (tier + vertical → signals)."""
from adcopilot.domain.launch.audience_signals import get_audience_signals
from adcopilot.domain.launch.budget_tier import BudgetTier
from adcopilot.domain.launch.templates import detect_vertical_from_description


def test_detect_vertical_returns_known_vertical():
    vertical = detect_vertical_from_description("nail salon beauty treatments hair")
    assert vertical in ("salon", "ecommerce", "restaurant", "legal", "medical", "generic")


def test_micro_budget_gets_no_audiences():
    vertical = detect_vertical_from_description("restaurant pizza delivery")
    signals = get_audience_signals(vertical, BudgetTier.MICRO)
    assert signals == []


def test_growth_budget_gets_audiences():
    vertical = detect_vertical_from_description("legal advice lawyer attorney")
    signals = get_audience_signals(vertical, BudgetTier.GROWTH)
    assert len(signals) >= 1
