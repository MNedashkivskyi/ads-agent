"""Detection rule: keyword quality score dropped ≥2 points vs. 7-day-ago snapshot."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

# Minimum QS drop (in points) to trigger the rule
_MIN_QS_DROP = 2
# Only flag keywords that have meaningful spend — QS on zero-spend keywords is unreliable
_MIN_COST_MICROS = 2_000_000  # €2


class QualityScoreDeteriorationRule:
    kind = RecommendationKind.QUALITY_SCORE_DETERIORATION
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.prev_keywords:
            return []

        # Key: (criterion_id, ad_group_id) — unique keyword instance
        prev_by_key = {(kw.criterion_id, kw.ad_group_id): kw for kw in ctx.prev_keywords}
        recs: list[Recommendation] = []

        for kw in ctx.keywords:
            if kw.quality_score is None:
                continue
            if kw.cost_micros < _MIN_COST_MICROS:
                continue

            prev = prev_by_key.get((kw.criterion_id, kw.ad_group_id))
            if prev is None or prev.quality_score is None:
                continue

            drop = prev.quality_score - kw.quality_score
            if drop < _MIN_QS_DROP:
                continue

            # Deteriorating QS raises CPCs. Estimate cost impact: each QS point
            # below 10 raises effective CPC by ~16% (Google's documented penalty).
            # We use the simpler proxy: extra cost vs. what the keyword would have
            # spent at the old QS, scaled to monthly.
            cpc_penalty_factor = 1 + (drop * 0.16)
            estimated_monthly_waste = int(kw.cost_micros * (cpc_penalty_factor - 1) * 4)

            target = {"criterion_id": kw.criterion_id, "ad_group_id": kw.ad_group_id}
            payload = {"criterion_id": kw.criterion_id, "ad_group_id": kw.ad_group_id}
            evidence = {
                "keyword_text": kw.text,
                "match_type": kw.match_type,
                "current_quality_score": kw.quality_score,
                "previous_quality_score": prev.quality_score,
                "qs_drop": drop,
                "cost_micros": kw.cost_micros,
            }
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=estimated_monthly_waste,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
