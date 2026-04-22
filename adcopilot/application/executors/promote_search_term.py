"""Executor: promote a high-converting search term as an exact-match keyword."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class PromoteSearchTermExecutor:
    """Adds a search term as an EXACT-match keyword in the specified ad group."""

    kind = RecommendationKind.PROMOTE_SEARCH_TERM

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        payload = rec.payload
        search_term: str = payload["search_term"]
        ad_group_id: int = int(payload["suggested_ad_group_id"])
        match_type: str = payload.get("suggested_match_type", "EXACT")

        criterion_id = await mutations.add_keyword(
            refresh_token=refresh_token,
            customer_id=customer_id,
            ad_group_id=ad_group_id,
            keyword_text=search_term,
            match_type=match_type,
        )

        return {
            "search_term": search_term,
            "ad_group_id": ad_group_id,
            "match_type": match_type,
            "criterion_id": criterion_id,
        }
