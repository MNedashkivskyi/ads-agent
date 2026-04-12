"""Detection rule: same keyword text added as both broad and exact/phrase in the same ad group."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)


class MatchTypeRedundancyRule:
    kind = RecommendationKind.MATCH_TYPE_REDUNDANCY
    severity = RecommendationSeverity.LOW

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        # Build ad group info lookup: ad_group_id -> (name, campaign_id)
        ag_info: dict[int, tuple[str, int]] = {
            ag.ad_group_id: (ag.name, ag.campaign_id) for ag in ctx.ad_groups
        }

        # Group match types by (ad_group_id, normalised keyword text)
        match_types_by_key: dict[tuple[int, str], set[str]] = defaultdict(set)
        for kw in ctx.keywords:
            if kw.status != "ENABLED":
                continue
            key = (kw.ad_group_id, kw.text.lower().strip())
            match_types_by_key[key].add(kw.match_type)

        recs: list[Recommendation] = []
        for (ad_group_id, kw_text), match_types in match_types_by_key.items():
            # Redundant when broad coexists with a more specific match type
            if "BROAD" not in match_types:
                continue
            if "EXACT" not in match_types and "PHRASE" not in match_types:
                continue

            ag_name, campaign_id = ag_info.get(ad_group_id, ("", 0))
            target = {
                "ad_group_id": ad_group_id,
                "campaign_id": campaign_id,
                "keyword_text": kw_text,
            }
            evidence = {
                "keyword_text": kw_text,
                "ad_group_name": ag_name,
                "match_types": sorted(match_types),
                "redundant_match_type": "BROAD",
            }
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target=target,
                    payload={
                        "ad_group_id": ad_group_id,
                        "campaign_id": campaign_id,
                        "keyword_text": kw_text,
                    },
                    evidence=evidence,
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
