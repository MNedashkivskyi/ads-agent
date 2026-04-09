"""Detection rule: surface every disapproved ad so it can be fixed or replaced."""

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


class DisapprovedAdRule:
    kind = RecommendationKind.FIX_DISAPPROVED_AD
    severity = RecommendationSeverity.CRITICAL

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        for ad in ctx.ads:
            if ad.status != "DISAPPROVED":
                continue

            target = {"ad_id": ad.ad_id, "ad_group_id": ad.ad_group_id}
            payload = {"ad_id": ad.ad_id, "ad_group_id": ad.ad_group_id}
            evidence = {
                "ad_id": ad.ad_id,
                "type": ad.type,
                "status": "DISAPPROVED",
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
