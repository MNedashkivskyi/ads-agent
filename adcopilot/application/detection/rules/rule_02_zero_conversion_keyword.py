"""Detection rule: pause keywords that spent 2x the account CPA with zero conversions."""

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


class ZeroConversionKeywordRule:
    kind = RecommendationKind.PAUSE_KEYWORD
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []
        avg_cpa = ctx.history.avg_cpa_micros

        if avg_cpa == 0:
            return recs

        threshold = 2 * avg_cpa

        for kw in ctx.keywords:
            if kw.conversions != 0:
                continue
            if kw.clicks < 30:
                continue
            if kw.cost_micros < threshold:
                continue

            target = {"criterion_id": kw.criterion_id, "ad_group_id": kw.ad_group_id}
            payload = {"criterion_id": kw.criterion_id, "ad_group_id": kw.ad_group_id}
            evidence = {
                "keyword_text": kw.text,
                "clicks": kw.clicks,
                "cost_micros": kw.cost_micros,
                "threshold_micros": threshold,
            }
            recs.append(
                self._make_rec(
                    account_id=ctx.account.id,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=kw.cost_micros,
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
