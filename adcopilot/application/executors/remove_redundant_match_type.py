"""Executor: pause a BROAD match keyword when EXACT/PHRASE already exists in the same ad group."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class RemoveRedundantMatchTypeExecutor:
    kind = RecommendationKind.MATCH_TYPE_REDUNDANCY

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        ad_group_id = int(rec.target["ad_group_id"])
        criterion_id = int(rec.target["criterion_id"])
        keyword_text = str(rec.evidence.get("keyword_text", ""))

        await mutations.pause_keyword(
            refresh_token=refresh_token,
            customer_id=customer_id,
            ad_group_id=ad_group_id,
            criterion_id=criterion_id,
        )
        return {
            "ad_group_id": ad_group_id,
            "criterion_id": criterion_id,
            "keyword_text": keyword_text,
            "action": "broad_keyword_paused",
        }
