"""Executor: pause an ad via Google Ads API."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class PauseAdExecutor:
    kind = RecommendationKind.PAUSE_AD

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        ad_group_id = int(rec.target["ad_group_id"])
        ad_id = int(rec.target["ad_id"])
        await mutations.pause_ad(
            refresh_token=refresh_token,
            customer_id=customer_id,
            ad_group_id=ad_group_id,
            ad_id=ad_id,
        )
        return {"ad_group_id": ad_group_id, "ad_id": ad_id, "action": "paused"}
