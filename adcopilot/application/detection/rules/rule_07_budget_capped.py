"""Detection rule: recommend a budget increase for campaigns consistently hitting their daily cap with positive ROAS."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from adcopilot.application.detection.base import DetectionContext
from adcopilot.application.detection.channel import is_search_campaign
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_CAP_PROXY_RATIO = 0.95
_MIN_ROAS = 1.0
_BUDGET_INCREASE_FACTOR = 1.2


class BudgetCappedRule:
    kind = RecommendationKind.INCREASE_BUDGET
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        for campaign in ctx.campaigns:
            if not is_search_campaign(campaign.channel_type):
                continue  # PMax/Shopping budgets handled by channel-aware rules
            if campaign.budget_micros <= 0:
                continue

            daily_avg_cost = campaign.cost_micros / 30
            if daily_avg_cost < campaign.budget_micros * _CAP_PROXY_RATIO:
                continue

            if campaign.conv_value <= 0 or campaign.cost_micros <= 0:
                continue

            roas = (campaign.conv_value * 1_000_000) / campaign.cost_micros
            if roas <= _MIN_ROAS:
                continue

            target = {"campaign_id": campaign.campaign_id}
            payload = {
                "campaign_id": campaign.campaign_id,
                "current_budget_micros": campaign.budget_micros,
                "suggested_budget_micros": int(campaign.budget_micros * _BUDGET_INCREASE_FACTOR),
            }
            evidence = {
                "campaign_name": campaign.name,
                "budget_micros": campaign.budget_micros,
                "cost_micros": campaign.cost_micros,
                "roas": round(roas, 2),
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
