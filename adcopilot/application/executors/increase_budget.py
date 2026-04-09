"""Executor: increase campaign budget via Google Ads API."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class IncreaseBudgetExecutor:
    kind = RecommendationKind.INCREASE_BUDGET

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        campaign_id = int(rec.payload["campaign_id"])
        new_budget_micros = int(rec.payload["suggested_budget_micros"])
        await mutations.update_campaign_budget(
            refresh_token=refresh_token,
            customer_id=customer_id,
            campaign_id=campaign_id,
            new_budget_micros=new_budget_micros,
        )
        return {
            "campaign_id": campaign_id,
            "new_budget_micros": new_budget_micros,
            "action": "budget_increased",
        }
