"""Rule 29 — Geo Exclusion.

Fires for locations that have accumulated > €50 spend, 0 conversions, and at
least 20 clicks over the 30-day window.  Recommends excluding those locations
to stop burning budget on non-converting geographies.
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

# Thresholds (cost in micros: €50 = 50_000_000)
_MIN_COST_MICROS = 50_000_000
_MIN_CLICKS = 20


class GeoExclusionRule:
    kind = RecommendationKind.GEO_EXCLUSION
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.geo_performance:
            return []

        # Aggregate per (campaign_id, location_id) across the window.
        cost: dict[tuple[int, int], int] = defaultdict(int)
        clicks: dict[tuple[int, int], int] = defaultdict(int)
        convs: dict[tuple[int, int], float] = defaultdict(float)

        for row in ctx.geo_performance:
            key = (row.campaign_id, row.location_id)
            cost[key] += row.cost_micros
            clicks[key] += row.clicks
            convs[key] += row.conversions

        recs: list[Recommendation] = []
        seen: set[tuple[int, int]] = set()

        for (campaign_id, location_id), total_cost in cost.items():
            key = (campaign_id, location_id)
            if key in seen:
                continue
            seen.add(key)

            total_clicks = clicks[key]
            total_convs = convs[key]

            if total_cost < _MIN_COST_MICROS:
                continue
            if total_clicks < _MIN_CLICKS:
                continue
            if total_convs > 0:
                continue

            campaign_name = str(campaign_id)
            for c in ctx.campaigns:
                if c.campaign_id == campaign_id:
                    campaign_name = c.name
                    break

            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target={"campaign_id": campaign_id, "location_id": location_id},
                    payload={"campaign_id": campaign_id, "location_id": location_id},
                    evidence={
                        "campaign_name": campaign_name,
                        "location_id": str(location_id),
                        "cost_micros": total_cost,
                        "clicks": total_clicks,
                        "conversions": total_convs,
                        "savings_micros": total_cost,
                    },
                    estimated_monthly_savings_micros=total_cost,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
