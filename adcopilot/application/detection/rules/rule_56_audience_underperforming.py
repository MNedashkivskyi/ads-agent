"""Detection rule 56 — Audience Underperforming.

Fires when an audience has a CPA more than 2× the campaign average and at
least 20 clicks.  Recommends applying a negative bid modifier to reduce spend
on this low-quality segment.
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

_CPA_RATIO_THRESHOLD = 2.0
_MIN_CLICKS = 20


class AudienceUnderperformingRule:
    kind = RecommendationKind.AUDIENCE_BID_ADJUSTMENT
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.audience_performance:
            return []

        rows = list(ctx.audience_performance)
        if not rows:
            return []

        # Only consider rows with conversions to compute CPA-based average
        eligible_for_avg = [
            r
            for r in rows
            if (getattr(r, "conversions", 0.0) or 0.0) > 0
            and (getattr(r, "clicks", 0) or 0) >= _MIN_CLICKS
        ]
        if not eligible_for_avg:
            return []

        total_cost = sum(getattr(r, "cost_micros", 0) or 0 for r in eligible_for_avg)
        total_conversions = sum(
            float(getattr(r, "conversions", 0.0) or 0.0) for r in eligible_for_avg
        )
        avg_cpa_micros = total_cost / total_conversions if total_conversions > 0 else None

        if avg_cpa_micros is None or avg_cpa_micros == 0:
            return []

        recommendations: list[Recommendation] = []
        for r in rows:
            clicks = getattr(r, "clicks", 0) or 0
            conversions = float(getattr(r, "conversions", 0.0) or 0.0)
            cost_micros = getattr(r, "cost_micros", 0) or 0

            if clicks < _MIN_CLICKS:
                continue
            if conversions == 0:
                continue

            audience_cpa_micros = cost_micros / conversions
            if audience_cpa_micros <= avg_cpa_micros * _CPA_RATIO_THRESHOLD:
                continue

            criterion_id = getattr(r, "criterion_id", None)
            campaign_id = getattr(r, "campaign_id", None)
            ad_group_id = getattr(r, "ad_group_id", None)

            ratio = audience_cpa_micros / avg_cpa_micros
            # Suggest negative modifier proportional to CPA excess, clamped to -70%
            suggested_modifier = max(0.30, round(1.0 - (ratio - 1.0) * 0.3, 2))
            estimated_savings = int(cost_micros * (1.0 - suggested_modifier))

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
                    f"Grupa odbiorców (criterion_id={criterion_id}) ma CPA "
                    f"{audience_cpa_micros / 1_000_000:.2f} PLN, czyli {ratio:.1f}× powyżej "
                    f"średniej konta ({avg_cpa_micros / 1_000_000:.2f} PLN) przy {clicks} kliknięciach. "
                    f"Zalecane zmniejszenie stawki do modyfikatora {suggested_modifier:.2f} "
                    f"(−{round((1.0 - suggested_modifier) * 100)}%)."
                ),
            }
            evidence = {
                "criterion_id": criterion_id,
                "audience_cpa_micros": int(audience_cpa_micros),
                "avg_cpa_micros": int(avg_cpa_micros),
                "cpa_ratio": round(ratio, 2),
                "clicks": clicks,
                "conversions": conversions,
                "cost_micros": cost_micros,
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
                    estimated_monthly_savings_micros=estimated_savings,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recommendations
