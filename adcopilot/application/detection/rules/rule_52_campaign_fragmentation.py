"""Detection rule 52 — Campaign Fragmentation.

Fires when ≥ 4 non-paused campaigns each have fewer than 10 clicks per day
on average over the last 30 days (i.e. < 300 clicks total in the window).
Too many low-traffic campaigns prevent Google's ML from learning effectively
and typically result in higher CPCs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_MIN_FRAGMENTED_CAMPAIGNS = 4
# < 10 clicks/day average over 30 days = < 300 clicks in the window
_MAX_CLICKS_THRESHOLD = 300


class CampaignFragmentationRule:
    kind = RecommendationKind.ORPHANED_CAMPAIGN
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        low_traffic: list = []

        for campaign in ctx.campaigns:
            if getattr(campaign, "status", "").upper() == "PAUSED":
                continue
            total_clicks = getattr(campaign, "clicks", 0) or 0
            if total_clicks < _MAX_CLICKS_THRESHOLD:
                low_traffic.append(campaign)

        if len(low_traffic) < _MIN_FRAGMENTED_CAMPAIGNS:
            return []

        campaign_ids = [str(getattr(c, "campaign_id", c)) for c in low_traffic]
        campaign_names = [getattr(c, "name", str(getattr(c, "campaign_id", ""))) for c in low_traffic]
        total_spend = sum(getattr(c, "cost_micros", 0) or 0 for c in low_traffic)
        # Estimated saving: consolidating campaigns typically lowers CPC by ~15 %
        estimated_savings = int(total_spend * 0.15)

        target = {"campaign_ids": campaign_ids}
        payload = {
            "fragmented_campaign_ids": campaign_ids,
            "fragmented_campaign_count": len(low_traffic),
        }
        evidence = {
            "fragmented_campaigns": [
                {
                    "campaign_id": str(getattr(c, "campaign_id", "")),
                    "name": getattr(c, "name", ""),
                    "clicks": getattr(c, "clicks", 0),
                }
                for c in low_traffic[:10]
            ],
            "total_fragmented": len(low_traffic),
        }

        return [
            Recommendation(
                id=RecommendationId(str(uuid.uuid4())),
                account_id=ctx.account.id,
                kind=self.kind,
                severity=self.severity,
                target=target,
                payload=payload,
                evidence=evidence,
                estimated_monthly_savings_micros=estimated_savings,
                created_at=datetime.now(tz=UTC),
                status=RecommendationStatus.PENDING,
            )
        ]
