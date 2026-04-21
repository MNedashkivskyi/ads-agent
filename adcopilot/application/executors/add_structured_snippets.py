"""Executor: add structured snippet extensions to a campaign via Google Ads API."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class AddStructuredSnippetsExecutor:
    kind = RecommendationKind.ADD_STRUCTURED_SNIPPETS

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        campaign_id = int(rec.target["campaign_id"])
        header: str = str(rec.payload.get("header", "Services"))
        values: list[str] = list(rec.payload.get("values", ["Service 1", "Service 2", "Service 3"]))
        ca_rns = await mutations.create_campaign_structured_snippets(
            refresh_token=refresh_token,
            customer_id=customer_id,
            campaign_id=campaign_id,
            header=header,
            values=values,
        )
        return {
            "campaign_id": campaign_id,
            "campaign_asset_resource_names": ca_rns,
            "action": "structured_snippets_added",
        }
