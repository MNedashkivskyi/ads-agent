"""Rule 30 — Ad Schedule Adjustment.

Fires for hours of the day that have accumulated > €20 spend and 0
conversions over the 30-day window.  Recommends adding a −100% bid
adjustment (effectively pausing ads) for those hours.
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

# €20 = 20_000_000 micros
_MIN_COST_MICROS = 20_000_000


class AdScheduleAdjustmentRule:
    kind = RecommendationKind.AD_SCHEDULE_ADJUSTMENT
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.hour_performance:
            return []

        # Aggregate per (campaign_id, hour_of_day).
        cost: dict[tuple[int, int], int] = defaultdict(int)
        convs: dict[tuple[int, int], float] = defaultdict(float)

        for row in ctx.hour_performance:
            key = (row.campaign_id, row.hour_of_day)
            cost[key] += row.cost_micros
            convs[key] += row.conversions

        recs: list[Recommendation] = []
        seen: set[tuple[int, int]] = set()

        for (campaign_id, hour), total_cost in cost.items():
            key = (campaign_id, hour)
            if key in seen:
                continue
            seen.add(key)

            if total_cost < _MIN_COST_MICROS:
                continue
            if convs[key] > 0:
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
                    target={"campaign_id": campaign_id, "hour_of_day": hour},
                    payload={"campaign_id": campaign_id, "hour_of_day": hour},
                    evidence={
                        "campaign_name": campaign_name,
                        "hour_of_day": hour,
                        "cost_micros": total_cost,
                        "conversions": convs[key],
                        "savings_micros": total_cost,
                    },
                    estimated_monthly_savings_micros=total_cost,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
