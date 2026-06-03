"""Rule 31 — Day-of-Week Bid Adjustment.

Fires when a particular day of the week has an average CPA more than 50%
above the account-level average CPA AND at least 10 conversions on that day
over the 30-day window.  Suggests reducing bids on that day.
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

_MIN_DOW_CONVERSIONS = 10
_CPA_EXCESS_RATIO = 1.5  # day CPA must be > 1.5× account avg CPA


class DayOfWeekBidAdjustmentRule:
    kind = RecommendationKind.DAY_OF_WEEK_BID_ADJUSTMENT
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.day_of_week_performance:
            return []

        # Account-level average CPA from history.
        if ctx.history.total_conversions <= 0:
            return []
        account_avg_cpa = ctx.history.avg_cpa_micros
        if account_avg_cpa <= 0:
            return []

        # Aggregate per (campaign_id, day_of_week).
        cost: dict[tuple[int, str], int] = defaultdict(int)
        convs: dict[tuple[int, str], float] = defaultdict(float)

        for row in ctx.day_of_week_performance:
            key = (row.campaign_id, row.day_of_week.upper())
            cost[key] += row.cost_micros
            convs[key] += row.conversions

        recs: list[Recommendation] = []
        seen: set[tuple[int, str]] = set()

        for (campaign_id, day), total_cost in cost.items():
            key = (campaign_id, day)
            if key in seen:
                continue
            seen.add(key)

            total_convs = convs[key]
            if total_convs < _MIN_DOW_CONVERSIONS:
                continue

            day_cpa = total_cost / total_convs
            if day_cpa <= _CPA_EXCESS_RATIO * account_avg_cpa:
                continue

            # Smart Bidding sets intraday/day-of-week bids automatically; manual
            # day-of-week adjustments are ignored — suppress for those campaigns.
            if bidding_mode_for(ctx.campaigns, campaign_id) is BiddingMode.SMART:
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
                    target={"campaign_id": campaign_id, "day_of_week": day},
                    payload={"campaign_id": campaign_id, "day_of_week": day},
                    evidence={
                        "campaign_name": campaign_name,
                        "day_of_week": day,
                        "day_cpa_micros": int(day_cpa),
                        "account_avg_cpa_micros": account_avg_cpa,
                        "ratio": round(day_cpa / account_avg_cpa, 2),
                        "conversions": total_convs,
                        "cost_micros": total_cost,
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
