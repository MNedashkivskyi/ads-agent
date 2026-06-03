"""Bidding-strategy classification for the detection engine.

Used to make manual-era rules (device/day/hour bid adjustments, match-type
redundancy, broad-match flags) bidding-strategy-aware. Under conversion-based
Smart Bidding, manual bid adjustments are ignored by Google, so emitting them
is noise/counterproductive.

Conservative by design: only the conversion-based automated strategies count as
SMART. Everything else — Maximize Clicks, Target Spend, Manual/Enhanced CPC,
and unknown/empty — is treated as MANUAL so we never wrongly suppress a
legitimate finding.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum


class BiddingMode(str, Enum):
    SMART = "SMART"
    MANUAL = "MANUAL"


# Conversion-based Smart Bidding strategies that ignore manual bid adjustments.
_SMART_STRATEGIES = {
    "MAXIMIZE_CONVERSIONS",
    "MAXIMIZE_CONVERSION_VALUE",
    "TARGET_CPA",
    "TARGET_ROAS",
}


def classify_bidding(strategy: str | None) -> BiddingMode:
    if not strategy:
        return BiddingMode.MANUAL
    return BiddingMode.SMART if strategy.strip().upper() in _SMART_STRATEGIES else BiddingMode.MANUAL


def is_smart_bidding(strategy: str | None) -> bool:
    return classify_bidding(strategy) is BiddingMode.SMART


def bidding_mode_for(campaigns: Iterable[object], campaign_id: int) -> BiddingMode:
    """Resolve the bidding mode for the campaign a finding belongs to.

    Returns MANUAL if the campaign can't be found (conservative — don't suppress).
    """
    for c in campaigns:
        if getattr(c, "campaign_id", None) == campaign_id:
            return classify_bidding(getattr(c, "bidding_strategy", None))
    return BiddingMode.MANUAL
