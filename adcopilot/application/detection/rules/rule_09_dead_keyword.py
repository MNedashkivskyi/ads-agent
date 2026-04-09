"""Detection rule: pause enabled keywords that received zero impressions in the past 30 days."""

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

_DAYS_CHECKED = 30


class DeadKeywordRule:
    kind = RecommendationKind.PAUSE_KEYWORD
    severity = RecommendationSeverity.LOW

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        for kw in ctx.keywords:
            if kw.impressions != 0:
                continue
            if kw.status != "ENABLED":
                continue

            target = {"criterion_id": kw.criterion_id, "ad_group_id": kw.ad_group_id}
            payload = {"criterion_id": kw.criterion_id, "ad_group_id": kw.ad_group_id}
            evidence = {
                "keyword_text": kw.text,
                "days_checked": _DAYS_CHECKED,
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
