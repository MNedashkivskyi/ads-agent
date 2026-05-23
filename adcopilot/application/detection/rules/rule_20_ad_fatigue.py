"""Detection rule: ad CTR dropped >25% week-over-week for the same ad with
stable impression volume — a signal that the creative has become stale and
users are increasingly ignoring it.

Ad fatigue is one of the most common reasons campaigns plateau: the same
copy that worked 3 months ago now gets scrolled past. Rotating in fresh
creative variations typically recovers CTR within 2-4 weeks.
"""

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

_MIN_CTR_DROP = 0.25  # CTR must fall ≥ 25% week-over-week
_MAX_IMPRESSION_CHANGE = 0.20  # Impressions must be stable ± 20%
_MIN_IMPRESSIONS = 500  # Require meaningful volume in both periods


class AdFatigueRule:
    kind = RecommendationKind.AD_FATIGUE
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.prev_ads:
            return []

        prev_by_id = {ad.ad_id: ad for ad in ctx.prev_ads}
        recs: list[Recommendation] = []

        for ad in ctx.ads:
            if ad.status != "ENABLED":
                continue
            if ad.impressions < _MIN_IMPRESSIONS:
                continue

            prev = prev_by_id.get(ad.ad_id)
            if prev is None or prev.impressions < _MIN_IMPRESSIONS:
                continue

            # Stable impressions: traffic volume hasn't changed dramatically
            impression_change = abs(ad.impressions - prev.impressions) / prev.impressions
            if impression_change > _MAX_IMPRESSION_CHANGE:
                continue

            curr_ctr = ad.clicks / ad.impressions
            prev_ctr = prev.clicks / prev.impressions if prev.impressions else 0.0

            if prev_ctr == 0:
                continue

            drop = (prev_ctr - curr_ctr) / prev_ctr
            if drop < _MIN_CTR_DROP:
                continue

            target = {"ad_id": ad.ad_id, "ad_group_id": ad.ad_group_id}
            payload = {"ad_id": ad.ad_id, "ad_group_id": ad.ad_group_id}
            evidence = {
                "ad_id": ad.ad_id,
                "current_ctr": round(curr_ctr, 4),
                "previous_ctr": round(prev_ctr, 4),
                "ctr_drop_pct": round(drop * 100, 1),
                "current_impressions": ad.impressions,
                "previous_impressions": prev.impressions,
                "ad_strength": ad.ad_strength,
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
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
