"""Detection rule: recommend bid adjustment when an audience has >20% higher conversion rate."""

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

_MIN_IMPRESSIONS = 100
_MIN_CONV_RATE_LIFT = 0.20  # 20% higher conv rate than account average


class AudienceBidAdjustmentRule:
    kind = RecommendationKind.AUDIENCE_BID_ADJUSTMENT
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.audience_performance:
            return []

        total_clicks = sum(k.clicks for k in ctx.keywords)
        total_convs = sum(k.conversions for k in ctx.keywords)
        if total_clicks == 0:
            return []
        account_conv_rate = total_convs / total_clicks

        recs: list[Recommendation] = []
        seen: set[int] = set()

        for aud in ctx.audience_performance:
            if aud.criterion_id in seen:
                continue
            if aud.impressions < _MIN_IMPRESSIONS or aud.clicks == 0:
                continue
            if account_conv_rate == 0:
                continue

            aud_conv_rate = aud.conversions / aud.clicks
            lift = (aud_conv_rate - account_conv_rate) / account_conv_rate
            if lift < _MIN_CONV_RATE_LIFT:
                continue

            seen.add(aud.criterion_id)
            suggested_modifier = min(round(lift * 100), 150)

            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target={
                        "criterion_id": aud.criterion_id,
                        "campaign_id": aud.campaign_id,
                        "ad_group_id": aud.ad_group_id,
                    },
                    payload={
                        "suggested_bid_modifier_pct": suggested_modifier,
                        "audience_conv_rate": round(aud_conv_rate, 4),
                        "account_conv_rate": round(account_conv_rate, 4),
                        "lift_pct": round(lift * 100, 1),
                    },
                    evidence={
                        "criterion_id": aud.criterion_id,
                        "impressions": aud.impressions,
                        "clicks": aud.clicks,
                        "conversions": aud.conversions,
                        "audience_conv_rate": round(aud_conv_rate, 4),
                        "account_conv_rate": round(account_conv_rate, 4),
                        "lift_pct": round(lift * 100, 1),
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
