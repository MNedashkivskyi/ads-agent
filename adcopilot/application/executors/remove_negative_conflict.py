"""Executor: remove a conflicting negative keyword blocking a positive keyword."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class RemoveNegativeConflictExecutor:
    kind = RecommendationKind.NEGATIVE_KEYWORD_CONFLICT

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        criterion_id = int(rec.target["criterion_id"])
        campaign_id = int(rec.target["campaign_id"])
        conflict_scope = str(rec.evidence.get("conflict_scope", "campaign"))
        keyword_text = str(rec.evidence["negative_keyword_text"])
        match_type = str(rec.evidence.get("negative_match_type", "EXACT"))
        ad_group_id = (
            int(rec.target.get("ad_group_id", 0)) if conflict_scope == "ad_group" else None
        )

        if conflict_scope == "ad_group" and ad_group_id:
            await mutations.remove_ad_group_negative_keyword(
                refresh_token=refresh_token,
                customer_id=customer_id,
                ad_group_id=ad_group_id,
                keyword_text=keyword_text,
                match_type=match_type,
            )
        else:
            await mutations.remove_campaign_negative_keyword(
                refresh_token=refresh_token,
                customer_id=customer_id,
                campaign_id=campaign_id,
                keyword_text=keyword_text,
                match_type=match_type,
            )

        return {
            "criterion_id": criterion_id,
            "campaign_id": campaign_id,
            "ad_group_id": ad_group_id,
            "keyword_text": keyword_text,
            "match_type": match_type,
            "conflict_scope": conflict_scope,
            "action": "negative_conflict_removed",
        }
