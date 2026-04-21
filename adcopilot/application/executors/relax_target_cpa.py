"""Executor: update target_cpa_micros on a TARGET_CPA campaign."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class RelaxTargetCpaExecutor:
    kind = RecommendationKind.RELAX_TARGET_CPA

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        campaign_id = int(rec.target["campaign_id"])
        suggested_target_cpa_micros = int(rec.evidence["suggested_target_cpa_micros"])
        original_target_cpa_micros = int(rec.evidence.get("current_target_cpa_micros", 0))

        await mutations.set_target_cpa(
            refresh_token=refresh_token,
            customer_id=customer_id,
            campaign_id=campaign_id,
            target_cpa_micros=suggested_target_cpa_micros,
        )
        return {
            "campaign_id": campaign_id,
            "original_target_cpa_micros": original_target_cpa_micros,
            "new_target_cpa_micros": suggested_target_cpa_micros,
            "action": "target_cpa_updated",
        }
