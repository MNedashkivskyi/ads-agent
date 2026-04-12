"""Rule 40 — Set Conversion Value.

Fires when an account records ≥ 10 conversions but `conv_value` is 0 across
all ENABLED campaigns.  Without conversion values Google cannot optimise for
ROAS, and the account owner cannot calculate true return on ad spend.

A single account-level recommendation is raised.
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

_MIN_CONVERSIONS = 10.0


class SetConversionValueRule:
    kind = RecommendationKind.SET_CONVERSION_VALUE
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        enabled = [c for c in ctx.campaigns if c.status == "ENABLED"]
        if not enabled:
            return []

        total_conversions = sum(c.conversions for c in enabled)
        total_conv_value = sum(c.conv_value for c in enabled)

        if total_conversions < _MIN_CONVERSIONS:
            return []
        if total_conv_value > 0:
            return []

        return [
            Recommendation(
                id=RecommendationId(str(uuid.uuid4())),
                account_id=ctx.account.id,  # type: ignore[arg-type]
                kind=self.kind,
                severity=self.severity,
                target={"account_id": str(ctx.account.id)},
                payload={"account_id": str(ctx.account.id)},
                evidence={
                    "total_conversions": total_conversions,
                    "total_conv_value": total_conv_value,
                },
                estimated_monthly_savings_micros=0,
                created_at=datetime.now(tz=UTC),
                status=RecommendationStatus.PENDING,
            )
        ]
