"""Audience signal mapping per vertical for observation-mode targeting.

MICRO tier gets no audiences — not enough data for meaningful signal.
MID and GROWTH tiers get in-market and affinity audiences in observation mode.

NOTE: Google Ads criterion IDs must be verified against current API docs before deployment.
"""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.domain.launch.budget_tier import BudgetTier


@dataclass(frozen=True)
class AudienceSignal:
    segment_id: int
    segment_name: str
    segment_type: str  # "IN_MARKET" | "AFFINITY" | "CUSTOM_INTENT"


VERTICAL_AUDIENCES: dict[str, list[AudienceSignal]] = {
    "salon": [
        AudienceSignal(80432, "Beauty & Personal Care", "IN_MARKET"),
        AudienceSignal(80433, "Hair Care", "IN_MARKET"),
    ],
    "ecommerce": [
        AudienceSignal(80538, "Apparel & Accessories", "IN_MARKET"),
        AudienceSignal(80539, "Shopping", "AFFINITY"),
    ],
    "restaurant": [
        AudienceSignal(80423, "Restaurants", "IN_MARKET"),
        AudienceSignal(80424, "Food Delivery", "IN_MARKET"),
    ],
    "legal": [
        AudienceSignal(80485, "Legal Services", "IN_MARKET"),
    ],
    "medical": [
        AudienceSignal(80455, "Health", "IN_MARKET"),
    ],
    "generic": [
        AudienceSignal(80435, "Business Services", "IN_MARKET"),
    ],
}


def get_audience_signals(vertical: str, tier: BudgetTier) -> list[AudienceSignal]:
    """Return observation-mode audience signals for a vertical and budget tier.

    MICRO tier returns empty list — insufficient budget for meaningful audience data.
    """
    if tier == BudgetTier.MICRO:
        return []
    return VERTICAL_AUDIENCES.get(vertical, VERTICAL_AUDIENCES["generic"])
