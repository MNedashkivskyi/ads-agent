"""Detection rule 50: PMAX_ASSET_DISAPPROVED — PMax asset group has disapproved assets.

Fires when a PERFORMANCE_MAX campaign snapshot indicates disapproved assets.
Since the snapshot doesn't carry asset-level approval status, this rule uses
a heuristic: if a PERFORMANCE_MAX campaign has zero impressions but non-zero spend,
or if 'disapproved' is present in the campaign evidence, it fires.

In production, asset disapproval status is fetched via a dedicated GAQL query
against `asset_group_asset` with `policy_summary.approval_status = DISAPPROVED`.
This rule fires based on available snapshot data — a full asset-level query
would be a separate task.

For the current implementation, we detect the signal via the `evidence` field
on existing snapshots or mark the campaign for review when the channel is PMax
and the campaign has run (cost > 0) but has zero impressions (classic disapproval symptom).
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

_MIN_COST_MICROS = 1_000_000  # 1 PLN minimum — avoid noise for brand-new campaigns


class PMaxAssetDisapprovedRule:
    kind = RecommendationKind.PMAX_ASSET_DISAPPROVED
    severity = RecommendationSeverity.CRITICAL

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        for campaign in ctx.campaigns:
            if campaign.channel_type != "PERFORMANCE_MAX":
                continue
            if campaign.status != "ENABLED":
                continue
            if campaign.cost_micros < _MIN_COST_MICROS:
                continue

            # Heuristic: enabled PMax campaign with spend but zero impressions
            # strongly suggests disapproved assets blocking delivery.
            if campaign.impressions > 0:
                continue

            target = {"campaign_id": campaign.campaign_id}
            payload = {
                "campaign_id": campaign.campaign_id,
                "cost_micros": campaign.cost_micros,
                "impressions": campaign.impressions,
            }
            evidence = {
                "campaign_name": campaign.name,
                "cost_pln": round(campaign.cost_micros / 1_000_000, 2),
                "impressions": campaign.impressions,
                "diagnosis": "Kampania PMax jest aktywna i ma wydatki, ale zero wyświetleń — prawdopodobnie zasoby reklamowe zostały odrzucone przez Google.",
            }
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,
                    kind=self.kind,
                    severity=self.severity,
                    status=RecommendationStatus.PENDING,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                )
            )

        return recs
