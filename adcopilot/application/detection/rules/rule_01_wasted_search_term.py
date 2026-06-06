"""Detection rule: flag search terms that consume budget with zero conversions and match waste signals."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from adcopilot.application.detection.base import DetectionContext
from adcopilot.application.detection.search_term_waste import is_wasteful_term
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)


class WastedSearchTermRule:
    kind = RecommendationKind.ADD_NEGATIVE_KEYWORD
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []
        # Anchor the waste floor to the client's target CPA when configured
        # (30% of an acceptable conversion cost); else 30% of historical avg CPA.
        econ = ctx.business_economics
        if econ is not None and getattr(econ, "target_cpa", None):
            basis_micros = int(econ.target_cpa * 1_000_000)
        else:
            basis_micros = ctx.history.avg_cpa_micros
        avg_cpa = ctx.history.avg_cpa_micros
        cost_threshold = basis_micros * 0.3

        for st in ctx.search_terms:
            # Canonical per-term waste predicate (shared with the search-terms
            # API via search_term_waste.is_wasteful_term). Signal words are a
            # booster on top of the cost/zero-conversion criteria; egregious
            # spend (more than one full acceptable CPA) fires on its own.
            if not is_wasteful_term(
                term=st.search_term,
                clicks=st.clicks,
                conversions=st.conversions,
                cost_micros=st.cost_micros,
                cost_floor_micros=cost_threshold,
                egregious_micros=basis_micros,
            ):
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
