"""Detection rule: ad group CTR dropped >30% week-over-week with stable impression volume."""

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

# CTR must drop by at least this fraction to trigger (0.30 = 30%)
_MIN_CTR_DROP = 0.30
# Impressions must be stable: change must be within ±20% to rule out volume shifts
_MAX_IMPRESSION_CHANGE = 0.20
# Minimum impressions in both periods to have statistically meaningful CTR
_MIN_IMPRESSIONS = 200


class CtrDeclineRule:
    kind = RecommendationKind.CTR_DECLINE
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.prev_ad_groups:
            return []

        prev_by_id = {ag.ad_group_id: ag for ag in ctx.prev_ad_groups}
        recs: list[Recommendation] = []

        for ag in ctx.ad_groups:
            prev = prev_by_id.get(ag.ad_group_id)
            if prev is None:
                continue

            if ag.impressions < _MIN_IMPRESSIONS or prev.impressions < _MIN_IMPRESSIONS:
                continue

            # Check impression volume is stable so the CTR change is real, not
            # just a traffic composition shift.
            impression_change = abs(ag.impressions - prev.impressions) / prev.impressions
            if impression_change > _MAX_IMPRESSION_CHANGE:
                continue

            curr_ctr = ag.clicks / ag.impressions if ag.impressions else 0.0
            prev_ctr = prev.clicks / prev.impressions if prev.impressions else 0.0

            if prev_ctr == 0:
                continue

            drop = (prev_ctr - curr_ctr) / prev_ctr
            if drop < _MIN_CTR_DROP:
                continue

            target = {"ad_group_id": ag.ad_group_id, "campaign_id": ag.campaign_id}
            payload = {"ad_group_id": ag.ad_group_id, "campaign_id": ag.campaign_id}
            evidence = {
                "ad_group_name": ag.name,
                "current_ctr": round(curr_ctr, 4),
                "previous_ctr": round(prev_ctr, 4),
                "ctr_drop_pct": round(drop * 100, 1),
                "current_impressions": ag.impressions,
                "previous_impressions": prev.impressions,
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
