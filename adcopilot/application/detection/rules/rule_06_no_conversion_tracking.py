"""Detection rule: alert when conversion tracking is missing or stale.

Fires CRITICAL in two scenarios:
  1. Missing: account has spend but zero conversions across all campaigns (original).
  2. Stale: account has ENABLED conversion actions but all report zero conversions
     in the last 7 days (new — indicates a broken tag or unreceived traffic).
"""

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
        if total_cost < _MIN_TOTAL_COST_MICROS:
            return recs

        total_conversions = sum(c.conversions for c in ctx.campaigns)

        # Scenario 1: no conversions at all (original check)
        if total_conversions == 0:
            recs.append(
                self._make_rec(
                    account_id=ctx.account.id,
                    target={"account_id": ctx.account.id},
                    payload={"account_id": ctx.account.id, "variant": "missing"},
                    evidence={
                        "total_cost_micros": total_cost,
                        "total_conversions": 0,
                        "variant": "missing",
                    },
                    estimated_monthly_savings_micros=0,
                )
            )
            return recs

        # Scenario 2: stale tracking — ENABLED actions with zero 7-day conversions
        enabled_actions = [
            a for a in ctx.conversion_actions if a.status == "ENABLED"
        ]
        if enabled_actions and all(a.all_conversions == 0 for a in enabled_actions):
            action_names = [a.name for a in enabled_actions]
            recs.append(
                self._make_rec(
                    account_id=ctx.account.id,
                    target={"account_id": ctx.account.id},
                    payload={
                        "account_id": ctx.account.id,
                        "variant": "stale",
                        "action_names": action_names,
                    },
                    evidence={
                        "total_cost_micros": total_cost,
                        "enabled_action_count": len(enabled_actions),
                        "action_names": action_names,
                        "variant": "stale",
                    },
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
