"""Detection rule 54 — Device Campaign Split.

Fires when mobile ad spend is more than 2× desktop spend in the last 30 days,
with both devices having at least 50 clicks each.  A large spend gap between
devices often indicates missing bid adjustments or separate device campaigns
would outperform the current unified structure.
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

_MIN_CLICKS_PER_DEVICE = 50
_COST_RATIO_THRESHOLD = 2.0


class DeviceCampaignSplitRule:
    kind = RecommendationKind.DEVICE_BID_ADJUSTMENT
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.device_performance:
            return []

        # Aggregate cost and clicks per device across all campaigns
        cost_by_device: dict[str, int] = defaultdict(int)
        clicks_by_device: dict[str, int] = defaultdict(int)

        for row in ctx.device_performance:
            device = getattr(row, "device", "").upper()
            cost_by_device[device] += getattr(row, "cost_micros", 0) or 0
            clicks_by_device[device] += getattr(row, "clicks", 0) or 0

        mobile_cost = cost_by_device.get("MOBILE", 0)
        desktop_cost = cost_by_device.get("DESKTOP", 0)
        mobile_clicks = clicks_by_device.get("MOBILE", 0)
        desktop_clicks = clicks_by_device.get("DESKTOP", 0)

        if mobile_clicks < _MIN_CLICKS_PER_DEVICE or desktop_clicks < _MIN_CLICKS_PER_DEVICE:
            return []

        if desktop_cost == 0:
            return []

        ratio = mobile_cost / desktop_cost
        if ratio <= _COST_RATIO_THRESHOLD:
            return []

        estimated_savings = int((mobile_cost - desktop_cost) * 0.20)

        target = {"account_id": str(ctx.account.id)}
        payload = {
            "mobile_cost_micros": mobile_cost,
            "desktop_cost_micros": desktop_cost,
            "ratio": round(ratio, 2),
        }
        evidence = {
            "mobile_cost_micros": mobile_cost,
            "desktop_cost_micros": desktop_cost,
            "mobile_clicks": mobile_clicks,
            "desktop_clicks": desktop_clicks,
            "cost_ratio": round(ratio, 2),
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
