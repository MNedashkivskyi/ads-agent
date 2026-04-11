"""Executor: change a keyword's match type via Google Ads API."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class ChangeMatchTypeExecutor:
    kind = RecommendationKind.CHANGE_MATCH_TYPE

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        ad_group_id = int(rec.payload["ad_group_id"])
        criterion_id = int(rec.payload["criterion_id"])
        new_match_type: str = str(rec.payload.get("suggested_match_type", "PHRASE"))
        old_match_type: str = str(rec.payload.get("current_match_type", "BROAD"))
        await mutations.change_keyword_match_type(
            refresh_token=refresh_token,
            customer_id=customer_id,
            ad_group_id=ad_group_id,
            criterion_id=criterion_id,
            match_type=new_match_type,
        )
        return {
            "ad_group_id": ad_group_id,
            "criterion_id": criterion_id,
            "old_match_type": old_match_type,
            "new_match_type": new_match_type,
            "action": "match_type_changed",
        }
