"""Detection rule: suggest switching from MAXIMIZE_CLICKS to MAXIMIZE_CONVERSIONS when conversion data is sufficient."""

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

_MIN_CONVERSIONS = 30
_SUGGESTED_STRATEGY = "MAXIMIZE_CONVERSIONS"


class WrongBiddingStrategyRule:
    kind = RecommendationKind.ADJUST_BIDDING_STRATEGY
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        for campaign in ctx.campaigns:
            if "MAXIMIZE_CLICKS" not in campaign.bidding_strategy.upper():
                continue
            if campaign.conversions < _MIN_CONVERSIONS:
                continue

            target = {"campaign_id": campaign.campaign_id}
            payload = {
                "campaign_id": campaign.campaign_id,
                "current_strategy": campaign.bidding_strategy,
                "suggested_strategy": _SUGGESTED_STRATEGY,
            }
            evidence = {
                "campaign_name": campaign.name,
                "conversions": campaign.conversions,
                "bidding_strategy": campaign.bidding_strategy,
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
