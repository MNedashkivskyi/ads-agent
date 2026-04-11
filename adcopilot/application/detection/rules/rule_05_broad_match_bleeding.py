"""Detection rule: detect broad-match keywords triggering many semantically unrelated search terms."""

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

_MIN_TRIGGERED_TERMS = 10
_MIN_BLEED_RATIO = 0.3
_JACCARD_THRESHOLD = 0.5


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


class BroadMatchBleedingRule:
    kind = RecommendationKind.CHANGE_MATCH_TYPE
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        # Index search terms by ad_group_id.  The Google Ads API does not
        # reliably populate matched_keyword_id, so we approximate by treating
        # all search terms in the same ad group as candidates for each broad
        # keyword in that group.  Jaccard similarity still filters out terms
        # that are genuinely unrelated to the keyword.
        st_by_ad_group: dict[int, list[Any]] = {}
        for st in ctx.search_terms:
            st_by_ad_group.setdefault(st.ad_group_id, []).append(st)

        for kw in ctx.keywords:
            if kw.match_type.upper() != "BROAD":
                continue

            triggered = st_by_ad_group.get(kw.ad_group_id, [])
            if len(triggered) < _MIN_TRIGGERED_TERMS:
                continue

            kw_tokens = set(kw.text.lower().split())
            unrelated = [
                st
                for st in triggered
                if _jaccard(set(st.search_term.lower().split()), kw_tokens) < _JACCARD_THRESHOLD
            ]

            bleed_ratio = len(unrelated) / len(triggered)
            if bleed_ratio < _MIN_BLEED_RATIO:
                continue

            sample_terms = [st.search_term for st in unrelated[:3]]
            savings = sum(st.cost_micros for st in unrelated) // 2

            target = {"criterion_id": kw.criterion_id, "ad_group_id": kw.ad_group_id}
            payload = {
                "criterion_id": kw.criterion_id,
                "ad_group_id": kw.ad_group_id,
                "current_match_type": kw.match_type.upper(),
                "suggested_match_type": "PHRASE",
            }
            evidence = {
                "keyword_text": kw.text,
                "bleed_ratio": round(bleed_ratio, 3),
                "sample_unrelated_terms": sample_terms,
            }
            recs.append(
                self._make_rec(
                    account_id=ctx.account.id,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=savings,
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
