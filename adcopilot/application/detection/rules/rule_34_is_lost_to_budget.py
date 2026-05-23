"""Rule 34 — Impression Share Lost to Budget.

Fires when a Search campaign loses more than 30% of eligible impressions
because its daily budget runs out before the end of the day.  Increasing
the budget (or redistributing it from lower-ROAS campaigns) would capture
meaningful missed traffic.

Uses the `INCREASE_BUDGET` kind (already defined for rule 07 which detects
budget utilisation).  To avoid deduplication collisions with rule 07 the
target dict includes the `signal` key so the hash is distinct.
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

_IS_BUDGET_THRESHOLD = 0.30  # > 30% IS lost to budget


class IsLostToBudgetRule:
    kind = RecommendationKind.INCREASE_BUDGET
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        for c in ctx.campaigns:
            if c.status != "ENABLED":
                continue
            if c.search_budget_lost_impression_share is None:
                continue
            if c.search_budget_lost_impression_share <= _IS_BUDGET_THRESHOLD:
                continue

            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    # "signal" key keeps this hash distinct from rule 07's target
                    target={"campaign_id": c.campaign_id, "signal": "budget_is"},
                    payload={"campaign_id": c.campaign_id},
                    evidence={
                        "campaign_name": c.name,
                        "search_budget_lost_impression_share": round(
                            c.search_budget_lost_impression_share, 4
                        ),
                        "budget_micros": c.budget_micros,
                        "cost_micros": c.cost_micros,
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
