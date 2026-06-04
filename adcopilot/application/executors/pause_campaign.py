"""Executor: pause a campaign (spend-safety protective action)."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class PauseCampaignExecutor:
    kind = RecommendationKind.PAUSE_CAMPAIGN

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        campaign_id = int(rec.target.get("campaign_id") or rec.payload["campaign_id"])
        await mutations.pause_campaign(
            refresh_token=refresh_token,
            customer_id=customer_id,
            campaign_id=campaign_id,
        )
        return {"campaign_id": campaign_id, "action": "campaign_paused"}
