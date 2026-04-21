"""Unit tests for BudgetTier enum and classify_budget_tier()."""

from decimal import Decimal

import pytest

from adcopilot.domain.launch.budget_tier import BudgetTier, classify_budget_tier


class TestBudgetTierEnum:
    def test_enum_values(self) -> None:
        assert BudgetTier.MICRO == "micro"
        assert BudgetTier.MID == "mid"
        assert BudgetTier.GROWTH == "growth"

    def test_three_tiers_exist(self) -> None:
        assert len(BudgetTier) == 3


class TestClassifyBudgetTier:
    # --- boundary: MID threshold (500) ---
    def test_just_below_mid_threshold_is_micro(self) -> None:
        assert classify_budget_tier(Decimal("499")) == BudgetTier.MICRO

    def test_at_mid_threshold_is_mid(self) -> None:
        assert classify_budget_tier(Decimal("500")) == BudgetTier.MID

    # --- boundary: GROWTH threshold (3000) ---
    def test_just_below_growth_threshold_is_mid(self) -> None:
        assert classify_budget_tier(Decimal("2999")) == BudgetTier.MID

    def test_at_growth_threshold_is_growth(self) -> None:
        assert classify_budget_tier(Decimal("3000")) == BudgetTier.GROWTH

    # --- edge: minimum and maximum ---
    def test_minimum_budget_is_micro(self) -> None:
        assert classify_budget_tier(Decimal("100")) == BudgetTier.MICRO

    def test_maximum_budget_is_growth(self) -> None:
        assert classify_budget_tier(Decimal("20000")) == BudgetTier.GROWTH

    # --- representative mid-range values ---
    def test_mid_range_micro(self) -> None:
        assert classify_budget_tier(Decimal("300")) == BudgetTier.MICRO

    def test_mid_range_mid(self) -> None:
        assert classify_budget_tier(Decimal("1500")) == BudgetTier.MID

    def test_mid_range_growth(self) -> None:
        assert classify_budget_tier(Decimal("8000")) == BudgetTier.GROWTH
