"""Rule 28 — Device Bid Adjustment.

Fires when mobile CPA is more than 2× desktop CPA and desktop has enough
conversions (≥ 30) to be statistically meaningful.  Suggests adding a
negative bid adjustment for mobile devices.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.application.detection.bidding import BiddingMode, bidding_mode_for
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_MIN_DESKTOP_CONVERSIONS = 30
_CPA_RATIO_THRESHOLD = 2.0  # mobile CPA must be > 2× desktop CPA


class DeviceBidAdjustmentRule:
    kind = RecommendationKind.DEVICE_BID_ADJUSTMENT
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.device_performance:
            return []

        # Aggregate cost/conversions per (campaign_id, device) across the window.
        cost: dict[tuple[int, str], int] = defaultdict(int)
        convs: dict[tuple[int, str], float] = defaultdict(float)

        for row in ctx.device_performance:
            key = (row.campaign_id, row.device.upper())
            cost[key] += row.cost_micros
            convs[key] += row.conversions

        # Group by campaign and compare MOBILE vs DESKTOP CPA.
        campaign_ids = {k[0] for k in cost}
        recs: list[Recommendation] = []

        for campaign_id in campaign_ids:
            desktop_cost = cost.get((campaign_id, "DESKTOP"), 0)
            desktop_conv = convs.get((campaign_id, "DESKTOP"), 0.0)
            mobile_cost = cost.get((campaign_id, "MOBILE"), 0)
            mobile_conv = convs.get((campaign_id, "MOBILE"), 0.0)

            if desktop_conv < _MIN_DESKTOP_CONVERSIONS:
                continue
            if mobile_conv <= 0:
                continue

            desktop_cpa = desktop_cost / desktop_conv
            mobile_cpa = mobile_cost / mobile_conv

            if mobile_cpa <= _CPA_RATIO_THRESHOLD * desktop_cpa:
                continue

            # Smart Bidding ignores manual device bid adjustments — it already
            # optimizes per-device. Emitting this would be noise/counterproductive.
            if bidding_mode_for(ctx.campaigns, campaign_id) is BiddingMode.SMART:
                continue

            # Find campaign name for context.
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
                    target={"campaign_id": campaign_id},
                    payload={"campaign_id": campaign_id},
                    evidence={
                        "campaign_name": campaign_name,
                        "mobile_cpa_micros": int(mobile_cpa),
                        "desktop_cpa_micros": int(desktop_cpa),
                        "ratio": round(mobile_cpa / desktop_cpa, 2),
                        "mobile_cost_micros": mobile_cost,
                        "mobile_conversions": mobile_conv,
                        "desktop_conversions": desktop_conv,
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
