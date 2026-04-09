"""Detection rule: pause expensive keywords with a low Quality Score (≤ 4)."""

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

_MIN_COST_MICROS = 10_000_000
_MAX_QUALITY_SCORE = 4


class LowQualityScoreKeywordRule:
    kind = RecommendationKind.PAUSE_KEYWORD
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        for kw in ctx.keywords:
            if kw.quality_score is None:
                continue
            if kw.quality_score > _MAX_QUALITY_SCORE:
                continue
            if kw.cost_micros < _MIN_COST_MICROS:
                continue

            target = {"criterion_id": kw.criterion_id, "ad_group_id": kw.ad_group_id}
            payload = {"criterion_id": kw.criterion_id, "ad_group_id": kw.ad_group_id}
            evidence = {
                "keyword_text": kw.text,
                "quality_score": kw.quality_score,
                "cost_micros": kw.cost_micros,
            }
            recs.append(
                self._make_rec(
                    account_id=ctx.account.id,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=kw.cost_micros // 2,
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
