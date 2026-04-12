"""Rule 35 — Impression Share Lost to Rank (Quality Score).

Fires when a Search campaign loses more than 30% of eligible impressions
because its Ad Rank is too low.  Ad Rank is a function of bid, quality score,
and expected impact of extensions.  The primary lever is improving Quality
Score (ad relevance, expected CTR, landing-page experience).
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

_IS_RANK_THRESHOLD = 0.30   # > 30% IS lost to rank


class IsLostToRankRule:
    kind = RecommendationKind.IMPROVE_QUALITY_SCORE
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        for c in ctx.campaigns:
            if c.status != "ENABLED":
                continue
            if c.search_rank_lost_impression_share is None:
                continue
            if c.search_rank_lost_impression_share <= _IS_RANK_THRESHOLD:
                continue

            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target={"campaign_id": c.campaign_id},
                    payload={"campaign_id": c.campaign_id},
                    evidence={
                        "campaign_name": c.name,
                        "search_rank_lost_impression_share": round(
                            c.search_rank_lost_impression_share, 4
                        ),
                        "impressions": c.impressions,
                        "cost_micros": c.cost_micros,
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
