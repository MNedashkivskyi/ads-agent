"""Executor: add a negative keyword to an ad group via Google Ads API."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class AddNegativeKeywordExecutor:
    kind = RecommendationKind.ADD_NEGATIVE_KEYWORD

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        ad_group_id = int(rec.target["ad_group_id"])
        keyword_text: str = str(
            rec.payload.get("negative_keyword", rec.target.get("search_term", ""))
        )
        match_type: str = str(rec.payload.get("match_type", "EXACT"))
        await mutations.add_ad_group_negative_keyword(
            refresh_token=refresh_token,
            customer_id=customer_id,
            ad_group_id=ad_group_id,
            keyword_text=keyword_text,
            match_type=match_type,
        )
        return {
            "ad_group_id": ad_group_id,
            "keyword_text": keyword_text,
            "match_type": match_type,
            "action": "added_negative",
        }
