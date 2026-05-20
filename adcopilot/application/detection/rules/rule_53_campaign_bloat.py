"""Detection rule 53 — Campaign Bloat.

Fires when a single campaign contains more than 8 ad groups.  Oversized
campaigns are harder to manage, dilute ad relevance, and typically push
Quality Scores down.
"""

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

_MAX_AD_GROUPS = 8


class CampaignBloatRule:
    kind = RecommendationKind.OVERSTUFFED_AD_GROUP
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        # Count ad groups per campaign using the snapshot data
        ad_groups_per_campaign: dict[int, list] = defaultdict(list)
        for ag in ctx.ad_groups:
            campaign_id = getattr(ag, "campaign_id", None)
            if campaign_id is not None:
                ad_groups_per_campaign[campaign_id].append(ag)

        recs: list[Recommendation] = []
        for campaign_id, ad_groups in ad_groups_per_campaign.items():
            if len(ad_groups) <= _MAX_AD_GROUPS:
                continue

            # Find the campaign name from ctx.campaigns
            campaign_name = ""
            for c in ctx.campaigns:
                if getattr(c, "campaign_id", None) == campaign_id:
                    campaign_name = getattr(c, "name", "")
                    break

            target = {"campaign_id": str(campaign_id)}
            payload = {
                "campaign_id": str(campaign_id),
                "ad_group_count": len(ad_groups),
            }
            evidence = {
                "campaign_id": str(campaign_id),
                "campaign_name": campaign_name,
                "ad_group_count": len(ad_groups),
                "ad_group_ids": [
                    str(getattr(ag, "ad_group_id", "")) for ag in ad_groups[:10]
                ],
            }

            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,
                    kind=self.kind,
                    severity=self.severity,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
