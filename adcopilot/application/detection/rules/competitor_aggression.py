"""Rule — Competitor Aggression.

Fires when an existing competitor's impression share has increased by more than
10 percentage points compared to 7 days prior.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_AGGRESSION_THRESHOLD = 0.10  # 10 pp increase


class CompetitorAggressionRule:
    kind = RecommendationKind.COMPETITOR_AGGRESSION
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.auction_insights:
            return []

        cutoff = ctx.snapshot_date - timedelta(days=7)

        # Group by (campaign_id, competitor_domain) → latest vs prior IS
        key_to_recent: dict[tuple, float] = {}
        key_to_prior: dict[tuple, float] = {}

        for row in ctx.auction_insights:
            key = (row["campaign_id"], row["competitor_domain"])
            is_val = row.get("impression_share") or 0.0
            if row["snapshot_date"] >= cutoff:
                if key not in key_to_recent or row["snapshot_date"] > cutoff:
                    key_to_recent[key] = is_val
            else:
                if key not in key_to_prior:
                    key_to_prior[key] = is_val

        recs: list[Recommendation] = []
        for key, current_is in key_to_recent.items():
            prior_is = key_to_prior.get(key)
            if prior_is is None:
                continue  # no prior data — NewCompetitor handles first appearance

            delta = current_is - prior_is
            if delta < _AGGRESSION_THRESHOLD:
                continue

            cid, domain = key
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target={"campaign_id": cid, "competitor_domain": domain},
                    payload={
                        "campaign_id": cid,
                        "competitor_domain": domain,
                        "current_impression_share": round(current_is, 4),
                        "prior_impression_share": round(prior_is, 4),
                        "delta_pp": round(delta * 100, 1),
                    },
                    evidence={
                        "competitor_domain": domain,
                        "current_impression_share": round(current_is, 4),
                        "prior_impression_share": round(prior_is, 4),
                        "delta_pp": round(delta * 100, 1),
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
