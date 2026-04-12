"""Rule 43 — Add Structured Snippets.

Fires for ENABLED campaigns that have at least 1 000 impressions but no
STRUCTURED_SNIPPET extension attached.  Structured snippets let advertisers
highlight specific features or products, increasing ad relevance and CTR.
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
_EXTENSION_TYPE = "STRUCTURED_SNIPPET"


class AddStructuredSnippetsRule:
    kind = RecommendationKind.ADD_STRUCTURED_SNIPPETS
    severity = RecommendationSeverity.LOW

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        # Build set of campaign_ids that already have structured snippet extensions.
        campaigns_with_snippets: set[int] = {
            ext.campaign_id
            for ext in ctx.campaign_extensions
            if ext.extension_type == _EXTENSION_TYPE
        }

        recs: list[Recommendation] = []

        for campaign in ctx.campaigns:
            if campaign.status != "ENABLED":
                continue
            if campaign.impressions < _MIN_IMPRESSIONS:
                continue
            if campaign.campaign_id in campaigns_with_snippets:
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
