"""Executor: add callout extensions to a campaign via Google Ads API."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class AddCalloutsExecutor:
    kind = RecommendationKind.ADD_CALLOUTS

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        campaign_id = int(rec.target["campaign_id"])
        callout_texts: list[str] = list(rec.payload.get("callout_texts", []))
        if not callout_texts:
            callout_texts = [
                "Free Consultation",
                "Trusted Experts",
                "Fast Response",
                "Quality Guaranteed",
            ]
        ca_rns = await mutations.create_campaign_callouts(
            refresh_token=refresh_token,
            customer_id=customer_id,
            campaign_id=campaign_id,
            callout_texts=callout_texts,
        )
        return {
            "campaign_id": campaign_id,
            "campaign_asset_resource_names": ca_rns,
            "action": "callouts_added",
        }
