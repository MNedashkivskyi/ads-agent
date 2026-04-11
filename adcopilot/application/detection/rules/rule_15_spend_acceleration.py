"""Detection rule: campaign spend grew >30% WoW while conversions stayed flat or declined."""

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

# Spend must have grown by at least this fraction week-over-week
_MIN_SPEND_GROWTH = 0.30
# Conversions must NOT have grown — flat is ±10%, decline is anything below
_MAX_CONVERSION_GROWTH = 0.10
# Require minimum spend in both periods to avoid noise from micro-budgets
_MIN_SPEND_MICROS = 5_000_000  # €5 / week


class SpendAccelerationRule:
    kind = RecommendationKind.SPEND_ACCELERATION
    severity = RecommendationSeverity.CRITICAL

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.prev_campaigns:
            return []

        prev_by_id = {c.campaign_id: c for c in ctx.prev_campaigns}
        recs: list[Recommendation] = []

        for camp in ctx.campaigns:
            prev = prev_by_id.get(camp.campaign_id)
            if prev is None:
                continue

            if camp.cost_micros < _MIN_SPEND_MICROS or prev.cost_micros < _MIN_SPEND_MICROS:
                continue

            spend_growth = (camp.cost_micros - prev.cost_micros) / prev.cost_micros
            if spend_growth < _MIN_SPEND_GROWTH:
                continue

            # Check conversions didn't grow proportionally
            if prev.conversions > 0:
                conv_growth = (camp.conversions - prev.conversions) / prev.conversions
            else:
                # No conversions in either period — still flag if spending more
                conv_growth = 0.0

            if conv_growth > _MAX_CONVERSION_GROWTH:
                continue

            # Extra spend vs. prior week, extrapolated to a month
            extra_weekly_spend = camp.cost_micros - prev.cost_micros
            estimated_monthly_waste = extra_weekly_spend * 4

            target = {"campaign_id": camp.campaign_id}
            payload = {"campaign_id": camp.campaign_id}
            evidence = {
                "campaign_name": camp.name,
                "current_cost_micros": camp.cost_micros,
                "previous_cost_micros": prev.cost_micros,
                "spend_growth_pct": round(spend_growth * 100, 1),
                "current_conversions": camp.conversions,
                "previous_conversions": prev.conversions,
                "conversion_growth_pct": round(conv_growth * 100, 1),
            }
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=estimated_monthly_waste,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
