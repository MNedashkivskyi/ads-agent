"""Detection rule 49: PMAX_LOW_ROAS — PMax campaign ROAS below target for 14+ days.

Fires when a PERFORMANCE_MAX campaign has ROAS < 1.0 (spending more than earning)
or below a user-configured target (defaulting to 2.0 for e-commerce context).
Uses the current snapshot's 30-day data as a proxy (no 14-day window available
in single-snapshot context; 14-day interpretation is a naming convention).
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

_DEFAULT_TARGET_ROAS = 2.0
_MIN_COST_MICROS = 10_000_000  # at least 10 PLN spent to avoid noise on new campaigns


class PMaxLowRoasRule:
    kind = RecommendationKind.PMAX_LOW_ROAS
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        for campaign in ctx.campaigns:
            if campaign.channel_type != "PERFORMANCE_MAX":
                continue
            if campaign.status not in ("ENABLED", "PAUSED"):
                continue
            if campaign.cost_micros < _MIN_COST_MICROS:
                continue
            if campaign.conv_value <= 0:
                # No conversions at all → ROAS effectively 0
                roas = 0.0
            else:
                roas = (campaign.conv_value * 1_000_000) / campaign.cost_micros

            if roas >= _DEFAULT_TARGET_ROAS:
                continue

            target = {"campaign_id": campaign.campaign_id}
            payload = {
                "campaign_id": campaign.campaign_id,
                "roas": round(roas, 2),
                "target_roas": _DEFAULT_TARGET_ROAS,
                "cost_micros": campaign.cost_micros,
                "conv_value": campaign.conv_value,
            }
            evidence = {
                "campaign_name": campaign.name,
                "roas": round(roas, 2),
                "target_roas": _DEFAULT_TARGET_ROAS,
                "cost_pln": round(campaign.cost_micros / 1_000_000, 2),
                "conversions_value_pln": round(campaign.conv_value, 2),
            }
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,
                    kind=self.kind,
                    severity=self.severity,
                    status=RecommendationStatus.PENDING,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                )
            )

        return recs
