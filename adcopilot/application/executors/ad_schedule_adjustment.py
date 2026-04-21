"""Executor: add -100% bid modifier for a specific hour to effectively pause ads."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class AdScheduleAdjustmentExecutor:
    kind = RecommendationKind.AD_SCHEDULE_ADJUSTMENT

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        campaign_id = int(rec.target["campaign_id"])
        hour_of_day = int(rec.target["hour_of_day"])
        await mutations.set_ad_schedule_bid_modifier(
            refresh_token=refresh_token,
            customer_id=customer_id,
            campaign_id=campaign_id,
            hour_of_day=hour_of_day,
            bid_modifier=-1.0,
        )
        return {
            "campaign_id": campaign_id,
            "hour_of_day": hour_of_day,
            "bid_modifier": -1.0,
            "action": "ad_schedule_bid_modifier_set",
        }
