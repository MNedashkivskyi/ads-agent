from __future__ import annotations

import pytest

from adcopilot.application.detection.bidding import (
    BiddingMode,
    bidding_mode_for,
    classify_bidding,
    is_smart_bidding,
)


@pytest.mark.parametrize(
    "strategy",
    ["MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE", "TARGET_CPA", "TARGET_ROAS", "target_cpa"],
)
def test_conversion_based_strategies_are_smart(strategy: str) -> None:
    assert classify_bidding(strategy) is BiddingMode.SMART
    assert is_smart_bidding(strategy) is True


@pytest.mark.parametrize(
    "strategy",
    ["MANUAL_CPC", "ENHANCED_CPC", "MAXIMIZE_CLICKS", "TARGET_SPEND", "", "UNKNOWN_XYZ"],
)
def test_non_conversion_or_unknown_is_manual(strategy: str) -> None:
    # Conservative: device/day bid adjustments still matter (or unknown) -> MANUAL,
    # so we never wrongly suppress a finding.
    assert classify_bidding(strategy) is BiddingMode.MANUAL
    assert is_smart_bidding(strategy) is False


class _Campaign:
    def __init__(self, campaign_id: int, bidding_strategy: str) -> None:
        self.campaign_id = campaign_id
        self.bidding_strategy = bidding_strategy


def test_bidding_mode_for_resolves_by_campaign_id() -> None:
    campaigns = [_Campaign(1, "TARGET_CPA"), _Campaign(2, "MANUAL_CPC")]
    assert bidding_mode_for(campaigns, 1) is BiddingMode.SMART
    assert bidding_mode_for(campaigns, 2) is BiddingMode.MANUAL


def test_bidding_mode_for_unknown_campaign_defaults_manual() -> None:
    assert bidding_mode_for([_Campaign(1, "TARGET_CPA")], 999) is BiddingMode.MANUAL
