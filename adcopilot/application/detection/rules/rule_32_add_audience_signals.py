"""Rule 32 — Add Audience Signals.

Fires for SEARCH campaigns that have zero observation audiences attached and
have accumulated at least 1 000 impressions.  Adding audience signals (even
in observation mode) gives Google's bidding algorithm more data to optimise
bids per audience segment.
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

_MIN_IMPRESSIONS = 1_000
_SEARCH_ADVERTISING_CHANNEL = "SEARCH"


class AddAudienceSignalsRule:
    kind = RecommendationKind.ADD_AUDIENCE_SIGNALS
    severity = RecommendationSeverity.LOW

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        # Build set of campaign_ids that already have at least one audience.
        campaigns_with_audience: set[int] = {
            row.campaign_id for row in ctx.audience_performance
        }

        recs: list[Recommendation] = []

        for campaign in ctx.campaigns:
            if campaign.status != "ENABLED":
                continue
            if campaign.channel_type != _SEARCH_ADVERTISING_CHANNEL:
                continue
            if campaign.campaign_id in campaigns_with_audience:
                continue
            if campaign.impressions < _MIN_IMPRESSIONS:
                continue

            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target={"campaign_id": campaign.campaign_id},
                    payload={"campaign_id": campaign.campaign_id},
                    evidence={
                        "campaign_name": campaign.name,
                        "impressions": campaign.impressions,
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
