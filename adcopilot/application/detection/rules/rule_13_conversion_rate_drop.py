"""Detection rule: campaign click-to-conversion rate dropped >25% week-over-week."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.application.detection.lag_guard import is_comparison_reliable
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

# Conversion rate must drop by at least this fraction to trigger (0.25 = 25%)
_MIN_CVR_DROP = 0.25
# Require minimum clicks in both periods for meaningful CVR data
_MIN_CLICKS = 50


class ConversionRateDropRule:
    kind = RecommendationKind.CONVERSION_RATE_DROP
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.prev_campaigns:
            return []

        prev_by_id = {c.campaign_id: c for c in ctx.prev_campaigns}
        recs: list[Recommendation] = []

        # Conversion-lag guard (see rule_12): downgrade to advisory for verticals
        # whose conversions settle slower than the week-over-week comparison gap.
        reliable = is_comparison_reliable(ctx.attribution_window_days)
        effective_severity = self.severity if reliable else RecommendationSeverity.LOW

        # Peak months bring more lower-intent traffic, naturally lowering CVR —
        # require a larger drop before firing. Unchanged in troughs.
        mult = seasonal_multiplier(ctx)
        min_cvr_drop = seasonal_relaxed_threshold(_MIN_CVR_DROP, mult)

        for camp in ctx.campaigns:
            prev = prev_by_id.get(camp.campaign_id)
            if prev is None:
                continue

            if camp.clicks < _MIN_CLICKS or prev.clicks < _MIN_CLICKS:
                continue

            curr_cvr = camp.conversions / camp.clicks
            prev_cvr = prev.conversions / prev.clicks

            if prev_cvr == 0:
                continue

            drop = (prev_cvr - curr_cvr) / prev_cvr
            if drop < min_cvr_drop:
                continue

            # Estimate lost conversions vs. prior week performance.
            expected_conversions = prev_cvr * camp.clicks
            lost_conversions = expected_conversions - camp.conversions
            # Value the lost conversions at the account's average CPA.
            lost_value_micros = int(lost_conversions * ctx.history.avg_cpa_micros * 4)

            target = {"campaign_id": camp.campaign_id}
            payload = {"campaign_id": camp.campaign_id}
            evidence = {
                "campaign_name": camp.name,
                "current_cvr": round(curr_cvr, 4),
                "previous_cvr": round(prev_cvr, 4),
                "cvr_drop_pct": round(drop * 100, 1),
                "current_clicks": camp.clicks,
                "current_conversions": camp.conversions,
                "lost_conversions_estimate": round(lost_conversions, 1),
                "conversions_maturing": not reliable,
                "attribution_window_days": ctx.attribution_window_days,
                "seasonal_multiplier": round(mult, 2),
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
                    estimated_monthly_savings_micros=max(0, lost_value_micros),
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
