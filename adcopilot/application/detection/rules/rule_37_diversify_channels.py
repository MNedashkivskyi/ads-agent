"""Rule 37 — Diversify Channels (Diminishing Returns).

Fires when a Search campaign increased spend by ≥ 20% week-over-week while
conversions grew by < 10% (or decreased).  This pattern indicates diminishing
returns: additional budget is not translating into proportional conversions,
suggesting the campaign has saturated available search demand.

The recommendation is to cap spend growth on this campaign and consider
allocating incremental budget to other channels (Display, YouTube, PMax).

Uses the 7-day-ago snapshot (`prev_campaigns`) already loaded by the
detection use case.
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

_MIN_COST_MICROS = 20_000_000  # current spend ≥ €20/week to be meaningful
_COST_GROWTH_THRESHOLD = 0.20  # cost must have grown ≥ 20%
_CONV_GROWTH_MAX = 0.10  # conversions grew < 10% (diminishing returns)


class DiversifyChannelsRule:
    kind = RecommendationKind.DIVERSIFY_CHANNELS
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.prev_campaigns:
            return []

        # Build lookup: campaign_id → prev snapshot
        prev_by_id = {c.campaign_id: c for c in ctx.prev_campaigns}

        recs: list[Recommendation] = []

        for c in ctx.campaigns:
            if c.status != "ENABLED":
                continue
            if c.cost_micros < _MIN_COST_MICROS:
                continue

            prev = prev_by_id.get(c.campaign_id)
            if prev is None or prev.cost_micros <= 0:
                continue

            cost_growth = (c.cost_micros - prev.cost_micros) / prev.cost_micros
            if cost_growth < _COST_GROWTH_THRESHOLD:
                continue

            # Conversion growth (handle prev=0 case: any conv now means infinite growth)
            if prev.conversions > 0:
                conv_growth = (c.conversions - prev.conversions) / prev.conversions
            else:
                # No prev conversions → if current also 0 it's diminishing (0% growth)
                conv_growth = 0.0 if c.conversions == 0 else float("inf")

            if conv_growth >= _CONV_GROWTH_MAX:
                continue

            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target={"campaign_id": c.campaign_id},
                    payload={"campaign_id": c.campaign_id},
                    evidence={
                        "campaign_name": c.name,
                        "current_cost_micros": c.cost_micros,
                        "prev_cost_micros": prev.cost_micros,
                        "cost_growth_pct": round(cost_growth * 100, 1),
                        "current_conversions": c.conversions,
                        "prev_conversions": prev.conversions,
                        "conv_growth_pct": round(conv_growth * 100, 1)
                        if conv_growth != float("inf")
                        else None,
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
