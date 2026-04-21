"""Executor: exclude a geographic location from a campaign."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class GeoExclusionExecutor:
    kind = RecommendationKind.GEO_EXCLUSION

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        campaign_id = int(rec.target["campaign_id"])
        location_id = int(rec.target["location_id"])
        await mutations.exclude_geo_location(
            refresh_token=refresh_token,
            customer_id=customer_id,
            campaign_id=campaign_id,
            location_id=location_id,
        )
        return {
            "campaign_id": campaign_id,
            "location_id": location_id,
            "action": "geo_excluded",
        }
