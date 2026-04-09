"""Detection rule: flag ad groups with only one active ad and meaningful impressions — add a variation for A/B testing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_MIN_IMPRESSIONS = 100


class SingleAdInGroupRule:
    kind = RecommendationKind.ADD_AD_VARIATION
    severity = RecommendationSeverity.LOW

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        # Map ad_group_id → active ads
        ads_by_group: dict[Any, list[Any]] = {}
        for ad in ctx.ads:
            if ad.status == "REMOVED":
                continue
            ads_by_group.setdefault(ad.ad_group_id, []).append(ad)

        # Map ad_group_id → ad_group object (for impressions, name, campaign_id)
        ag_by_id: dict[Any, Any] = {ag.ad_group_id: ag for ag in ctx.ad_groups}

        for ad_group_id, active_ads in ads_by_group.items():
            if len(active_ads) != 1:
                continue

            ad_group = ag_by_id.get(ad_group_id)
            if ad_group is None:
                continue
            if ad_group.impressions < _MIN_IMPRESSIONS:
                continue

            target = {"ad_group_id": ad_group_id}
            payload = {
                "ad_group_id": ad_group_id,
                "campaign_id": ad_group.campaign_id,
            }
            evidence = {
                "ad_group_name": ad_group.name,
                "impressions": ad_group.impressions,
                "enabled_ad_count": 1,
            }
            recs.append(
                self._make_rec(
                    account_id=ctx.account.id,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=0,
                )
            )

        return recs

    def _make_rec(
        self,
        account_id: str,
        target: dict[str, Any],
        payload: dict[str, Any],
        evidence: dict[str, Any],
        estimated_monthly_savings_micros: int,
    ) -> Recommendation:
        return Recommendation(
            id=RecommendationId(str(uuid.uuid4())),
            account_id=account_id,  # type: ignore[arg-type]
            kind=self.kind,
            severity=self.severity,
            target=target,
            payload=payload,
            evidence=evidence,
            estimated_monthly_savings_micros=estimated_monthly_savings_micros,
            created_at=datetime.now(tz=UTC),
            status=RecommendationStatus.PENDING,
        )
