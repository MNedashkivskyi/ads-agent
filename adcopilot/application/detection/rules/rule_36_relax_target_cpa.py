"""Rule 36 — Relax Target CPA.

Fires when a TARGET_CPA campaign has a target that is less than 50% of the
account-level average CPA.  A target this aggressive tells Google Smart
Bidding to only bid on extremely high-intent users, which dramatically
shrinks auction participation and conversion volume.

Requires at least some spend (≥ €5) to confirm the campaign is active.
Also requires the campaign to have fewer than 5 conversions in the window —
if it already achieves the tight target it may not need relaxing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.application.detection.channel import is_search_campaign
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_TARGET_CPA_RATIO = 0.50  # target < 50% of account avg → too tight
_MIN_SPEND_MICROS = 5_000_000  # campaign must have spent at least €5
_MAX_CONVERSIONS = 5.0  # if already converting well, skip


class RelaxTargetCpaRule:
    kind = RecommendationKind.RELAX_TARGET_CPA
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        account_avg_cpa = ctx.history.avg_cpa_micros
        if account_avg_cpa <= 0:
            return []

        recs: list[Recommendation] = []

        for c in ctx.campaigns:
            if not is_search_campaign(c.channel_type):
                continue  # PMax/Shopping tCPA handled by channel-aware rules
            if c.status != "ENABLED":
                continue
            if c.bidding_strategy != "TARGET_CPA":
                continue
            if c.target_cpa_micros is None:
                continue
            if c.cost_micros < _MIN_SPEND_MICROS:
                continue
            if c.conversions > _MAX_CONVERSIONS:
                continue
            if c.target_cpa_micros >= account_avg_cpa * _TARGET_CPA_RATIO:
                continue

            suggested_target = int(account_avg_cpa * 0.75)  # 75% of avg as safer starting point

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
                        "target_cpa_micros": c.target_cpa_micros,
                        "account_avg_cpa_micros": account_avg_cpa,
                        "ratio": round(c.target_cpa_micros / account_avg_cpa, 2),
                        "suggested_target_cpa_micros": suggested_target,
                        "conversions": c.conversions,
                        "cost_micros": c.cost_micros,
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
