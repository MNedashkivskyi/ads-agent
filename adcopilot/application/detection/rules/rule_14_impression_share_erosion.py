"""Detection rule: search impression share dropped >15 pp week-over-week."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.application.detection.seasonal import (
    seasonal_multiplier,
    seasonal_relaxed_threshold,
)
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

# Drop in search impression share (as absolute percentage points) that triggers
# this rule.  e.g. 0.15 means a drop from 60% to 45% IS triggers it.
_MIN_IS_DROP_PP = 0.15
# Only flag if the current IS is below this ceiling — no point alerting on a
# campaign that lost IS but still has 90%+.
_MAX_CURRENT_IS = 0.85


class ImpressionShareErosionRule:
    kind = RecommendationKind.IMPRESSION_SHARE_EROSION
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.prev_campaigns:
            return []

        prev_by_id = {c.campaign_id: c for c in ctx.prev_campaigns}
        recs: list[Recommendation] = []

        # In peak months competitors bid harder and IS naturally erodes; require a
        # larger drop before flagging. Unchanged in troughs.
        mult = seasonal_multiplier(ctx)
        min_is_drop_pp = seasonal_relaxed_threshold(_MIN_IS_DROP_PP, mult)

        for camp in ctx.campaigns:
            curr_is = camp.search_impression_share
            if curr_is is None:
                continue

            prev = prev_by_id.get(camp.campaign_id)
            if prev is None or prev.search_impression_share is None:
                continue

            prev_is = prev.search_impression_share
            drop = prev_is - curr_is

            if drop < min_is_drop_pp:
                continue
            if curr_is > _MAX_CURRENT_IS:
                continue

            # Determine primary cause from the lost-IS breakdown.
            budget_lost = camp.search_budget_lost_impression_share or 0.0
            rank_lost = camp.search_rank_lost_impression_share or 0.0
            primary_cause = "budget" if budget_lost > rank_lost else "ad rank / quality score"

            target = {"campaign_id": camp.campaign_id}
            payload = {
                "campaign_id": camp.campaign_id,
                "primary_cause": primary_cause,
            }
            evidence = {
                "campaign_name": camp.name,
                "current_impression_share": round(curr_is, 3),
                "previous_impression_share": round(prev_is, 3),
                "drop_pp": round(drop, 3),
                "budget_lost_impression_share": round(budget_lost, 3),
                "rank_lost_impression_share": round(rank_lost, 3),
                "primary_cause": primary_cause,
                "seasonal_multiplier": round(mult, 2),
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
