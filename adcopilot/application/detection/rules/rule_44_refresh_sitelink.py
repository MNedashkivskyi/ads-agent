"""Rule 44 — Refresh Sitelink.

Fires when a sitelink asset has accumulated ≥500 impressions over the past 30
days but its aggregated CTR is below 0.5 %.  A low-CTR sitelink is either
irrelevant to the audience, has stale copy, or points to a poor landing page —
any of which lowers overall ad quality.
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

_MIN_IMPRESSIONS = 500
# 0.5 % expressed as a fraction
_MAX_CTR = 0.005


class RefreshSitelinkRule:
    kind = RecommendationKind.REFRESH_SITELINK
    severity = RecommendationSeverity.LOW

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.sitelink_performance:
            return []

        # Aggregate impressions + clicks per (campaign_id, asset_id) across 30 days.
        totals: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0])
        for snap in ctx.sitelink_performance:
            key = (snap.campaign_id, snap.asset_id)
            totals[key][0] += snap.impressions
            totals[key][1] += snap.clicks

        recs: list[Recommendation] = []

        for (campaign_id, asset_id), (impressions, clicks) in totals.items():
            if impressions < _MIN_IMPRESSIONS:
                continue
            ctr = clicks / impressions
            if ctr >= _MAX_CTR:
                continue

            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target={"campaign_id": campaign_id, "asset_id": asset_id},
                    payload={"campaign_id": campaign_id, "asset_id": asset_id},
                    evidence={
                        "impressions": impressions,
                        "clicks": clicks,
                        "ctr": round(ctr, 5),
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
