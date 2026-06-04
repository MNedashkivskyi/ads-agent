"""Module 11 — Performance Max / Shopping asset-group + feed health (advisory).

Three channel-aware rules grounded in the asset-group / listing-group data ingested
in SH0. All advisory (notify + explain in Polish); no automated mutation.

- PMAX_ASSET_GROUP_WEAK     — ad strength POOR/AVERAGE → add headlines/images/videos.
- PMAX_ASSET_GROUP_LIMITED  — primary status LIMITED/NOT_ELIGIBLE → fix assets/policy.
- PMAX_FEED_SEGMENTATION    — spending PMax/Shopping campaign with only a catch-all
                              listing group → segment products to control bids/budget.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.application.detection.channel import is_pmax_or_shopping
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_WEAK_AD_STRENGTHS = {"POOR", "AVERAGE"}
_LIMITED_STATUSES = {"LIMITED", "NOT_ELIGIBLE"}
_MIN_COST_MICROS = 10_000_000  # 10 PLN spent before flagging segmentation


def _rec(ctx: DetectionContext, kind, severity, target, payload, evidence) -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=ctx.account.id,
        kind=kind,
        severity=severity,
        status=RecommendationStatus.PENDING,
        target=target,
        payload=payload,
        evidence=evidence,
        estimated_monthly_savings_micros=0,
        created_at=datetime.now(tz=UTC),
    )


class PMaxAssetGroupWeakRule:
    kind = RecommendationKind.PMAX_ASSET_GROUP_WEAK
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []
        for ag in getattr(ctx, "asset_groups", []):
            if ag.status not in ("ENABLED", "PAUSED"):
                continue
            if (ag.ad_strength or "").upper() not in _WEAK_AD_STRENGTHS:
                continue
            recs.append(
                _rec(
                    ctx,
                    self.kind,
                    self.severity,
                    {"asset_group_id": ag.asset_group_id, "campaign_id": ag.campaign_id},
                    {"asset_group_id": ag.asset_group_id, "ad_strength": ag.ad_strength},
                    {"asset_group_name": ag.name, "ad_strength": ag.ad_strength},
                )
            )
        return recs


class PMaxAssetGroupLimitedRule:
    kind = RecommendationKind.PMAX_ASSET_GROUP_LIMITED
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []
        for ag in getattr(ctx, "asset_groups", []):
            if ag.status != "ENABLED":
                continue
            if (ag.primary_status or "").upper() not in _LIMITED_STATUSES:
                continue
            recs.append(
                _rec(
                    ctx,
                    self.kind,
                    self.severity,
                    {"asset_group_id": ag.asset_group_id, "campaign_id": ag.campaign_id},
                    {"asset_group_id": ag.asset_group_id, "primary_status": ag.primary_status},
                    {"asset_group_name": ag.name, "primary_status": ag.primary_status},
                )
            )
        return recs


class PMaxFeedSegmentationRule:
    kind = RecommendationKind.PMAX_FEED_SEGMENTATION
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        listing_groups = getattr(ctx, "listing_groups", [])
        if not listing_groups:
            return []
        # Group listing-group filters by campaign.
        by_campaign: dict[int, list] = {}
        for lg in listing_groups:
            by_campaign.setdefault(lg.campaign_id, []).append(lg)

        spend_by_campaign = {
            c.campaign_id: c
            for c in ctx.campaigns
            if is_pmax_or_shopping(c.channel_type) and c.cost_micros >= _MIN_COST_MICROS
        }

        recs: list[Recommendation] = []
        for campaign_id, groups in by_campaign.items():
            campaign = spend_by_campaign.get(campaign_id)
            if campaign is None:
                continue
            # Only a catch-all → no product segmentation.
            if all(g.is_catch_all for g in groups):
                recs.append(
                    _rec(
                        ctx,
                        self.kind,
                        self.severity,
                        {"campaign_id": campaign_id},
                        {"campaign_id": campaign_id, "listing_group_count": len(groups)},
                        {
                            "campaign_name": campaign.name,
                            "cost_pln": round(campaign.cost_micros / 1_000_000, 2),
                        },
                    )
                )
        return recs
