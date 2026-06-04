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

        # Anchor waste to the client's target CPA when configured: a keyword that
        # spent a full acceptable CPA with zero conversions is wasted. Otherwise
        # fall back to 2× the historical average CPA.
        econ = ctx.business_economics
        target_cpa_micros = (
            int(econ.target_cpa * 1_000_000)
            if econ is not None and getattr(econ, "target_cpa", None)
            else None
        )
        avg_cpa = ctx.history.avg_cpa_micros
        if target_cpa_micros:
            threshold = target_cpa_micros
        elif avg_cpa > 0:
            threshold = 2 * avg_cpa
        else:
            return recs

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
                "threshold_basis": "target_cpa" if target_cpa_micros else "avg_cpa_2x",
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
