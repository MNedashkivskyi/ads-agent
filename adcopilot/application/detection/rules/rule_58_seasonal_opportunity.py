"""Detection rule 58 — Seasonal Peak Opportunity.

Fires 14 days before a predicted seasonal peak: current month multiplier < 1.0
but next month multiplier > 1.1.  Recommends increasing budget proactively to
capture elevated demand.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

# Polish market seasonal multipliers (month number → multiplier)
_MULTIPLIERS: dict[int, float] = {
    1: 0.8, 2: 0.9, 3: 1.1, 4: 1.1,
    5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0,
    9: 1.1, 10: 1.0, 11: 1.3, 12: 1.4,
}

_MONTH_NAMES_PL: dict[int, str] = {
    1: "styczeń", 2: "luty", 3: "marzec", 4: "kwiecień",
    5: "maj", 6: "czerwiec", 7: "lipiec", 8: "sierpień",
    9: "wrzesień", 10: "październik", 11: "listopad", 12: "grudzień",
}

_WINDOW_DAYS = 14


class SeasonalOpportunityRule:
    kind = RecommendationKind.INCREASE_BUDGET
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        today = date.today()
        current_month = today.month
        next_month = current_month % 12 + 1

        current_multiplier = _MULTIPLIERS.get(current_month, 1.0)
        next_multiplier = _MULTIPLIERS.get(next_month, 1.0)

        # Only fire when current month is below baseline and next month is a peak
        if not (current_multiplier < 1.0 and next_multiplier > 1.1):
            return []

        # Check if we are within 14 days of the next month
        if next_month == 1:
            next_month_start = date(today.year + 1, 1, 1)
        else:
            next_month_start = date(today.year, next_month, 1)

        days_until_peak = (next_month_start - today).days
        if days_until_peak > _WINDOW_DAYS:
            return []

        recommended_increase_pct = round((next_multiplier - 1.0) * 100, 1)
        next_month_name = _MONTH_NAMES_PL[next_month]

        target = {"account_id": str(ctx.account.id), "trigger": "seasonal_opportunity"}
        payload = {
            "current_month": current_month,
            "next_month": next_month,
            "current_multiplier": current_multiplier,
            "next_multiplier": next_multiplier,
            "days_until_peak": days_until_peak,
            "recommended_increase_pct": recommended_increase_pct,
            "description_pl": (
                f"Za {days_until_peak} dni rozpoczyna się {next_month_name} — "
                f"miesiąc o wskaźniku sezonowości {next_multiplier:.1f}x (o {recommended_increase_pct}% "
                "powyżej normy na polskim rynku). Zaleca się zwiększenie budżetów kampanii przed "
                "nadchodzącym szczytem, aby zmaksymalizować udział w ruchu."
            ),
            "recommendation_pl": (
                f"Zwiększ budżety kampanii o ok. {recommended_increase_pct}% przed początkiem "
                f"{next_month_name}. Skonfiguruj harmonogram budżetu tak, aby wyższe stawki "
                "były aktywne od 1. dnia miesiąca szczytowego."
            ),
        }
        evidence = {
            "current_month_multiplier": current_multiplier,
            "next_month_multiplier": next_multiplier,
            "days_until_peak": days_until_peak,
            "next_month": next_month_name,
        }

        return [
            Recommendation(
                id=RecommendationId(str(uuid.uuid4())),
                account_id=ctx.account.id,
                kind=self.kind,
                severity=self.severity,
                target=target,
                payload=payload,
                evidence=evidence,
                estimated_monthly_savings_micros=0,
                created_at=datetime.now(tz=UTC),
                status=RecommendationStatus.PENDING,
            )
        ]
