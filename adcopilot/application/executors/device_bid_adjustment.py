"""Executor: apply a negative mobile bid modifier to a campaign."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class DeviceBidAdjustmentExecutor:
    kind = RecommendationKind.DEVICE_BID_ADJUSTMENT

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        campaign_id = int(rec.target["campaign_id"])
        mobile_cpa = float(rec.evidence.get("mobile_cpa_micros", 0))
        desktop_cpa = float(rec.evidence.get("desktop_cpa_micros", 1))

        if desktop_cpa <= 0:
            desktop_cpa = 1.0

        raw_modifier = -(1.0 - desktop_cpa / mobile_cpa) if mobile_cpa > 0 else -0.5
        bid_modifier = max(-0.90, min(-0.20, raw_modifier))

        await mutations.set_device_bid_modifier(
            refresh_token=refresh_token,
            customer_id=customer_id,
            campaign_id=campaign_id,
            bid_modifier=bid_modifier,
        )
        return {
            "campaign_id": campaign_id,
            "bid_modifier": bid_modifier,
            "mobile_cpa_micros": mobile_cpa,
            "desktop_cpa_micros": desktop_cpa,
            "action": "device_bid_modifier_set",
        }
