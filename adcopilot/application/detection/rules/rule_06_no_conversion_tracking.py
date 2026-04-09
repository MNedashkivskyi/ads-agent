"""Detection rule: alert when significant spend is recorded but no conversions exist account-wide."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_MIN_TOTAL_COST_MICROS = 100_000_000


class NoConversionTrackingRule:
    kind = RecommendationKind.ENABLE_CONVERSION_TRACKING
    severity = RecommendationSeverity.CRITICAL

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        total_cost = sum(c.cost_micros for c in ctx.campaigns)
        total_conversions = sum(c.conversions for c in ctx.campaigns)

        if total_cost < _MIN_TOTAL_COST_MICROS:
            return recs
        if total_conversions != 0:
            return recs

        target = {"account_id": ctx.account.id}
        payload = {"account_id": ctx.account.id}
        evidence = {
            "total_cost_micros": total_cost,
            "total_conversions": 0,
        }
        recs.append(
            self._make_rec(
                account_id=ctx.account.id,
                target=target,
                payload=payload,
                evidence=evidence,
                estimated_monthly_savings_micros=0,
            )
        )

        return recs

    def _make_rec(
        self,
        account_id: str,
        target: dict[str, Any],
        payload: dict[str, Any],
        evidence: dict[str, Any],
        estimated_monthly_savings_micros: int,
    ) -> Recommendation:
        return Recommendation(
            id=RecommendationId(str(uuid.uuid4())),
            account_id=account_id,  # type: ignore[arg-type]
            kind=self.kind,
            severity=self.severity,
            target=target,
            payload=payload,
            evidence=evidence,
            estimated_monthly_savings_micros=estimated_monthly_savings_micros,
            created_at=datetime.now(tz=UTC),
            status=RecommendationStatus.PENDING,
        )
