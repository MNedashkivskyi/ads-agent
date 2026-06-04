"""Detection rule: campaign cost-per-conversion spiked >50% week-over-week."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.application.detection.lag_guard import is_comparison_reliable
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

# CPA must increase by at least this fraction to trigger (0.50 = 50%)
_MIN_CPA_SPIKE = 0.50
# Require at least this many conversions in both periods for statistical validity
_MIN_CONVERSIONS = 5


class CpaSpikeRule:
    kind = RecommendationKind.CPA_SPIKE
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.prev_campaigns:
            return []

        prev_by_id = {c.campaign_id: c for c in ctx.prev_campaigns}
        recs: list[Recommendation] = []

        # Conversion-lag guard: for long-cycle verticals the latest window is
        # undercounted, so a measured CPA spike is likely an attribution-lag
        # artefact. Keep the signal but downgrade it to advisory and annotate.
        reliable = is_comparison_reliable(ctx.attribution_window_days)
        effective_severity = self.severity if reliable else RecommendationSeverity.LOW

        for camp in ctx.campaigns:
            prev = prev_by_id.get(camp.campaign_id)
            if prev is None:
                continue

            if camp.conversions < _MIN_CONVERSIONS or prev.conversions < _MIN_CONVERSIONS:
                continue

            curr_cpa = camp.cost_micros / camp.conversions
            prev_cpa = prev.cost_micros / prev.conversions

            if prev_cpa == 0:
                continue

            spike = (curr_cpa - prev_cpa) / prev_cpa
            if spike < _MIN_CPA_SPIKE:
                continue

            # Estimated extra monthly spend caused by the CPA increase.
            # Assumes same conversion volume at higher CPA.
            extra_cost_micros = int((curr_cpa - prev_cpa) * camp.conversions * 4)

            target = {"campaign_id": camp.campaign_id}
            payload = {"campaign_id": camp.campaign_id}
            evidence = {
                "campaign_name": camp.name,
                "current_cpa_micros": int(curr_cpa),
                "previous_cpa_micros": int(prev_cpa),
                "cpa_spike_pct": round(spike * 100, 1),
                "current_conversions": camp.conversions,
                "previous_conversions": prev.conversions,
                "conversions_maturing": not reliable,
                "attribution_window_days": ctx.attribution_window_days,
            }
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=effective_severity,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=extra_cost_micros,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
