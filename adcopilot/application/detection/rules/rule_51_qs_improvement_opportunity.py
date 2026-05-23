"""Detection rule: ≥ 3 keywords in same ad group with QS ≤ 5 and combined impressions > 500/month."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_MAX_QS = 5
_MIN_AD_GROUP_KEYWORDS = 3
_MIN_COMBINED_IMPRESSIONS = 500


class QSImprovementOpportunityRule:
    kind = RecommendationKind.IMPROVE_QUALITY_SCORE
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        # Group low-QS keywords by ad_group_id
        groups: dict[int, list] = defaultdict(list)
        for kw in ctx.keywords:
            if kw.quality_score is None:
                continue
            if kw.quality_score > _MAX_QS:
                continue
            groups[kw.ad_group_id].append(kw)

        recs: list[Recommendation] = []
        for ad_group_id, keywords in groups.items():
            if len(keywords) < _MIN_AD_GROUP_KEYWORDS:
                continue
            total_impressions = sum(kw.impressions for kw in keywords)
            if total_impressions < _MIN_COMBINED_IMPRESSIONS:
                continue

            avg_qs = sum(kw.quality_score for kw in keywords if kw.quality_score) / len(keywords)
            criterion_ids = [kw.criterion_id for kw in keywords]

            # Estimate savings: 30% CPC reduction on combined spend
            total_cost = sum(getattr(kw, "cost_micros", 0) for kw in keywords)
            estimated_savings = int(total_cost * 0.30)

            target = {"ad_group_id": ad_group_id, "criterion_ids": criterion_ids}
            payload = {
                "ad_group_id": ad_group_id,
                "criterion_ids": criterion_ids,
                "auto_create_qs_plan": True,
            }
            evidence = {
                "keyword_count": len(keywords),
                "avg_qs": round(avg_qs, 1),
                "total_impressions": total_impressions,
                "keywords": [
                    {"text": kw.text, "qs": kw.quality_score, "impressions": kw.impressions}
                    for kw in keywords[:5]
                ],
            }
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,
                    kind=self.kind,
                    severity=self.severity,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=estimated_savings,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
