"""Detection rule: suggest audience expansion when impression share is saturated (>90%)."""

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

_IMPRESSION_SHARE_THRESHOLD = 0.90
_MIN_IMPRESSIONS = 500


class AudienceExpansionRule:
    kind = RecommendationKind.AUDIENCE_EXPANSION
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.audience_performance:
            return []

        campaign_impression_share: dict[int, float] = {}
        for c in ctx.campaigns:
            if c.search_impression_share is not None:
                campaign_impression_share[c.campaign_id] = c.search_impression_share

        recs: list[Recommendation] = []
        seen_campaigns: set[int] = set()

        for aud in ctx.audience_performance:
            if aud.campaign_id in seen_campaigns:
                continue
            if aud.impressions < _MIN_IMPRESSIONS:
                continue

            is_val = campaign_impression_share.get(aud.campaign_id)
            if is_val is None or is_val < _IMPRESSION_SHARE_THRESHOLD:
                continue

            seen_campaigns.add(aud.campaign_id)
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target={"campaign_id": aud.campaign_id},
                    payload={
                        "impression_share": round(is_val, 4),
                        "suggestion": "add_similar_audiences",
                    },
                    evidence={
                        "campaign_id": aud.campaign_id,
                        "impression_share": round(is_val, 4),
                        "audience_impressions": aud.impressions,
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
