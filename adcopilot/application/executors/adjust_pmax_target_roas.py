"""Executor: set target ROAS on a Performance Max / Shopping campaign (safe auto-fix).

Used by ADJUST_PMAX_TARGET_ROAS recommendations, which propose tightening a low-ROAS
PMax/Shopping campaign toward the account's target. Spend-guarded: loosening tROAS
beyond the configured bound is refused before this runs.
"""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class AdjustPmaxTargetRoasExecutor:
    kind = RecommendationKind.ADJUST_PMAX_TARGET_ROAS

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        campaign_id = int(rec.payload["campaign_id"])
        target_roas = float(rec.payload["target_roas"])
        await mutations.set_target_roas(
            refresh_token=refresh_token,
            customer_id=customer_id,
            campaign_id=campaign_id,
            target_roas=target_roas,
        )
        return {
            "campaign_id": campaign_id,
            "target_roas": target_roas,
            "action": "pmax_target_roas_set",
        }
