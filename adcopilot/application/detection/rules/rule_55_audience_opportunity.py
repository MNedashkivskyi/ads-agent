"""Detection rule 55 — Audience Bid Opportunity.

Fires when an audience has a conversion rate more than 30% above the campaign
average but no bid modifier is set (bid_modifier == 1.0 or missing).  This
indicates an untapped opportunity to increase bids for high-performing segments.
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

_CONV_RATE_THRESHOLD = 1.30  # 30% above average
_MIN_CLICKS = 10


class AudienceOpportunityRule:
    kind = RecommendationKind.AUDIENCE_BID_ADJUSTMENT
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.audience_performance:
            return []

        rows = list(ctx.audience_performance)
        if not rows:
            return []

        # Compute average conv_rate across all audience rows with sufficient clicks
        eligible = [r for r in rows if (getattr(r, "clicks", 0) or 0) >= _MIN_CLICKS]
        if not eligible:
            return []

        total_clicks = sum(getattr(r, "clicks", 0) or 0 for r in eligible)
        total_conversions = sum(getattr(r, "conversions", 0.0) or 0.0 for r in eligible)
        avg_conv_rate = total_conversions / total_clicks if total_clicks > 0 else 0.0

        if avg_conv_rate == 0.0:
            return []

        recommendations: list[Recommendation] = []
        for r in eligible:
            clicks = getattr(r, "clicks", 0) or 0
            conversions = float(getattr(r, "conversions", 0.0) or 0.0)
            conv_rate = conversions / clicks if clicks > 0 else 0.0
            bid_modifier = float(getattr(r, "bid_modifier", 1.0) or 1.0)

            if conv_rate > avg_conv_rate * _CONV_RATE_THRESHOLD and abs(bid_modifier - 1.0) < 0.01:
                criterion_id = getattr(r, "criterion_id", None)
                campaign_id = getattr(r, "campaign_id", None)
                ad_group_id = getattr(r, "ad_group_id", None)

                suggested_modifier = min(round(conv_rate / avg_conv_rate, 2), 2.0)

                target = {
                    "account_id": str(ctx.account.id),
                    "criterion_id": str(criterion_id),
                    "campaign_id": str(campaign_id),
                }
                payload = {
                    "criterion_id": criterion_id,
                    "campaign_id": campaign_id,
                    "ad_group_id": ad_group_id,
                    "suggested_bid_modifier": suggested_modifier,
                    "description_pl": (
                        f"Grupa odbiorców (criterion_id={criterion_id}) osiąga współczynnik "
                        f"konwersji {conv_rate:.2%}, czyli {conv_rate / avg_conv_rate:.1f}× "
                        f"powyżej średniej konta ({avg_conv_rate:.2%}), ale nie ma ustawionego "
                        "modyfikatora stawki. Zalecane zwiększenie stawki o "
                        f"{round((suggested_modifier - 1.0) * 100)}%."
                    ),
                }
                evidence = {
                    "criterion_id": criterion_id,
                    "conv_rate": round(conv_rate, 4),
                    "avg_conv_rate": round(avg_conv_rate, 4),
                    "ratio": round(conv_rate / avg_conv_rate, 2),
                    "clicks": clicks,
                    "conversions": conversions,
                    "current_bid_modifier": bid_modifier,
                }
                recommendations.append(
                    Recommendation(
                        id=RecommendationId(str(uuid.uuid4())),
                        account_id=ctx.account.id,
                        kind=self.kind,
                        severity=self.severity,
                        target=target,
                        payload=payload,
                        evidence=evidence,
                        estimated_monthly_savings_micros=0,
                        created_at=datetime.now(tz=UTC),
                        status=RecommendationStatus.PENDING,
                    )
                )

        return recommendations
