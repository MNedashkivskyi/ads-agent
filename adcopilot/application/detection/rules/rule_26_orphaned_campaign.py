"""Detection rule: campaign is enabled and budgeted but has no active ad groups."""

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

# Ad groups in these statuses are not actively delivering ads
_INACTIVE_STATUSES = {"PAUSED", "REMOVED"}


class OrphanedCampaignRule:
    kind = RecommendationKind.ORPHANED_CAMPAIGN
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        # Group ad groups by campaign
        ag_by_campaign: dict[int, list] = defaultdict(list)
        for ag in ctx.ad_groups:
            ag_by_campaign[ag.campaign_id].append(ag)

        recs: list[Recommendation] = []

        for campaign in ctx.campaigns:
            if campaign.status != "ENABLED":
                continue
            if campaign.budget_micros == 0:
                continue

            ad_groups = ag_by_campaign.get(campaign.campaign_id, [])
            active_ad_groups = [ag for ag in ad_groups if ag.status not in _INACTIVE_STATUSES]

            if ad_groups and active_ad_groups:
                # Has at least one active ad group — not orphaned
                continue

            # Either zero ad groups or all inactive
            target = {"campaign_id": campaign.campaign_id}
            evidence = {
                "campaign_name": campaign.name,
                "budget_micros": campaign.budget_micros,
                "ad_group_count": len(ad_groups),
                "active_ad_groups": 0,
            }
            # Estimate: daily budget wasted for a full month
            estimated_savings = campaign.budget_micros * 30

            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target=target,
                    payload={"campaign_id": campaign.campaign_id},
                    evidence=evidence,
                    estimated_monthly_savings_micros=estimated_savings,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
