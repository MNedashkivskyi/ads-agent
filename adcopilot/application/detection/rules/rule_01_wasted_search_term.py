"""Detection rule: flag search terms that consume budget with zero conversions and match waste signals."""

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

_WASTE_SIGNALS = ["free", "jobs", "salary", "how to", "diy", "wikipedia", "youtube"]


class WastedSearchTermRule:
    kind = RecommendationKind.ADD_NEGATIVE_KEYWORD
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []
        avg_cpa = ctx.history.avg_cpa_micros
        cost_threshold = avg_cpa * 0.3

        for st in ctx.search_terms:
            if st.clicks < 5:
                continue
            if st.conversions != 0:
                continue
            if st.cost_micros <= cost_threshold:
                continue

            term_lower = st.search_term.lower()
            if not any(signal in term_lower for signal in _WASTE_SIGNALS):
                continue

            target = {"ad_group_id": st.ad_group_id, "search_term": st.search_term}
            payload = {
                "negative_keyword": st.search_term,
                "level": "AD_GROUP",
                "match_type": "EXACT",
            }
            evidence = {
                "search_term": st.search_term,
                "clicks": st.clicks,
                "cost_micros": st.cost_micros,
                "conversions": 0,
                "avg_cpa_micros": avg_cpa,
            }
            recs.append(
                self._make_rec(
                    account_id=ctx.account.id,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=st.cost_micros,
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
