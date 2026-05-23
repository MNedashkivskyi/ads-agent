"""Unit tests for resolve_bidding_strategy() — all 7 logic branches."""


from adcopilot.domain.launch.bidding_resolver import (
    BiddingRecommendation,
    resolve_bidding_strategy,
)
from adcopilot.domain.launch.budget_tier import BudgetTier

# ---------------------------------------------------------------------------
# No conversion tracking — always MAXIMIZE_CLICKS, no upgrade
# ---------------------------------------------------------------------------


class TestNoConversionTracking:
    def test_micro_no_tracking(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.MICRO, False, 0)
        assert rec.initial_strategy == "MAXIMIZE_CLICKS"
        assert rec.upgrade_strategy is None
        assert rec.upgrade_threshold_conversions is None

    def test_mid_no_tracking(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.MID, False, 100)
        assert rec.initial_strategy == "MAXIMIZE_CLICKS"
        assert rec.upgrade_strategy is None

    def test_growth_no_tracking(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.GROWTH, False, 50)
        assert rec.initial_strategy == "MAXIMIZE_CLICKS"
        assert rec.upgrade_strategy is None


# ---------------------------------------------------------------------------
# MICRO tier — always MAXIMIZE_CLICKS with upgrade at 30
# ---------------------------------------------------------------------------


class TestMicroTier:
    def test_micro_new_account(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.MICRO, True, 0)
        assert rec.initial_strategy == "MAXIMIZE_CLICKS"
        assert rec.upgrade_strategy == "MAXIMIZE_CONVERSIONS"
        assert rec.upgrade_threshold_conversions == 30

    def test_micro_with_some_conversions(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.MICRO, True, 15)
        assert rec.initial_strategy == "MAXIMIZE_CLICKS"
        assert rec.upgrade_threshold_conversions == 30

    def test_micro_with_many_conversions_still_maximize_clicks(self) -> None:
        # Even with 50 conversions, MICRO tier stays on MAXIMIZE_CLICKS initially
        rec = resolve_bidding_strategy(BudgetTier.MICRO, True, 50)
        assert rec.initial_strategy == "MAXIMIZE_CLICKS"
        assert rec.upgrade_strategy == "MAXIMIZE_CONVERSIONS"


# ---------------------------------------------------------------------------
# MID tier — three sub-branches
# ---------------------------------------------------------------------------


class TestMidTier:
    def test_mid_below_15_conversions(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.MID, True, 0)
        assert rec.initial_strategy == "MAXIMIZE_CLICKS"
        assert rec.upgrade_strategy == "MAXIMIZE_CONVERSIONS"
        assert rec.upgrade_threshold_conversions == 30

    def test_mid_exactly_14_conversions(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.MID, True, 14.9)
        assert rec.initial_strategy == "MAXIMIZE_CLICKS"

    def test_mid_exactly_15_conversions(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.MID, True, 15)
        assert rec.initial_strategy == "MAXIMIZE_CONVERSIONS"
        assert rec.upgrade_strategy == "TARGET_CPA"
        assert rec.upgrade_threshold_conversions == 50

    def test_mid_between_15_and_30(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.MID, True, 22)
        assert rec.initial_strategy == "MAXIMIZE_CONVERSIONS"
        assert rec.upgrade_strategy == "TARGET_CPA"
        assert rec.upgrade_threshold_conversions == 50

    def test_mid_30_or_more_conversions(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.MID, True, 30)
        assert rec.initial_strategy == "MAXIMIZE_CONVERSIONS"
        assert rec.upgrade_strategy == "TARGET_CPA"
        assert rec.upgrade_threshold_conversions == 50

    def test_mid_100_conversions(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.MID, True, 100)
        assert rec.initial_strategy == "MAXIMIZE_CONVERSIONS"


# ---------------------------------------------------------------------------
# GROWTH tier — two sub-branches
# ---------------------------------------------------------------------------


class TestGrowthTier:
    def test_growth_below_30_conversions(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.GROWTH, True, 0)
        assert rec.initial_strategy == "MAXIMIZE_CONVERSIONS"
        assert rec.upgrade_strategy == "TARGET_CPA"
        assert rec.upgrade_threshold_conversions == 50

    def test_growth_exactly_29_conversions(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.GROWTH, True, 29.9)
        assert rec.initial_strategy == "MAXIMIZE_CONVERSIONS"

    def test_growth_exactly_30_conversions(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.GROWTH, True, 30)
        assert rec.initial_strategy == "TARGET_CPA"
        assert rec.upgrade_strategy is None
        assert rec.upgrade_threshold_conversions is None

    def test_growth_high_volume(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.GROWTH, True, 200)
        assert rec.initial_strategy == "TARGET_CPA"


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


class TestReturnType:
    def test_returns_bidding_recommendation(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.MID, True, 0)
        assert isinstance(rec, BiddingRecommendation)

    def test_rationale_is_non_empty(self) -> None:
        rec = resolve_bidding_strategy(BudgetTier.GROWTH, True, 50)
        assert rec.rationale
