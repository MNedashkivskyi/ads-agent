"""Executor: switch a campaign to a better bidding strategy via Google Ads API."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class AdjustBiddingStrategyExecutor:
    kind = RecommendationKind.ADJUST_BIDDING_STRATEGY

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        campaign_id = int(rec.payload["campaign_id"])
        new_strategy: str = str(rec.payload["suggested_strategy"])
        old_strategy: str = str(rec.payload.get("current_strategy", "MAXIMIZE_CLICKS"))
        await mutations.set_campaign_bidding_strategy(
            refresh_token=refresh_token,
            customer_id=customer_id,
            campaign_id=campaign_id,
            bidding_strategy=new_strategy,
        )
        return {
            "campaign_id": campaign_id,
            "old_strategy": old_strategy,
            "new_strategy": new_strategy,
            "action": "bidding_strategy_changed",
        }
