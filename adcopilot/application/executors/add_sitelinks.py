"""Executor: add sitelink extensions to a campaign via Google Ads API."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class AddSitelinksExecutor:
    kind = RecommendationKind.ADD_SITELINKS

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        campaign_id = int(rec.target["campaign_id"])
        sitelinks: list[dict[str, str]] = list(rec.payload.get("sitelinks", []))
        if not sitelinks:
            sitelinks = [
                {
                    "link_text": "Our Services",
                    "description1": "See what we offer",
                    "description2": "Professional solutions",
                    "final_url": "https://example.com/services",
                },
                {
                    "link_text": "Contact Us",
                    "description1": "Get in touch today",
                    "description2": "Fast response guaranteed",
                    "final_url": "https://example.com/contact",
                },
            ]
        ca_rns = await mutations.create_campaign_sitelinks(
            refresh_token=refresh_token,
            customer_id=customer_id,
            campaign_id=campaign_id,
            sitelinks=sitelinks,
        )
        return {
            "campaign_id": campaign_id,
            "campaign_asset_resource_names": ca_rns,
            "action": "sitelinks_added",
        }
