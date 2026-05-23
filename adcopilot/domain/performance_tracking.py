"""Domain entities for tracking recommendation performance over time."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import RecommendationId

PerformanceBaselineId = str
PerformanceComparisonId = str

EntityType = Literal["campaign", "ad_group", "keyword"]
Verdict = Literal["IMPROVED", "NEUTRAL", "DEGRADED"]


@dataclass(frozen=True)
class PerformanceBaseline:
    id: PerformanceBaselineId
    recommendation_id: RecommendationId
    account_id: AccountId
    entity_type: EntityType
    entity_id: int
    baseline_date: date
    cost_micros: int
    clicks: int
    impressions: int
    conversions: float
    conv_value: float
    cpa_micros: int
    ctr: float
    captured_at: datetime

    @classmethod
    def create(
        cls,
        recommendation_id: RecommendationId,
        account_id: AccountId,
        entity_type: EntityType,
        entity_id: int,
        baseline_date: date,
        cost_micros: int,
        clicks: int,
        impressions: int,
        conversions: float,
        conv_value: float,
        captured_at: datetime,
    ) -> PerformanceBaseline:
        cpa_micros = int(cost_micros / conversions) if conversions > 0 else 0
        ctr = clicks / impressions if impressions > 0 else 0.0
        return cls(
            id=str(uuid.uuid4()),
            recommendation_id=recommendation_id,
            account_id=account_id,
            entity_type=entity_type,
            entity_id=entity_id,
            baseline_date=baseline_date,
            cost_micros=cost_micros,
            clicks=clicks,
            impressions=impressions,
            conversions=conversions,
            conv_value=conv_value,
            cpa_micros=cpa_micros,
            ctr=ctr,
            captured_at=captured_at,
        )


@dataclass(frozen=True)
class PerformanceComparison:
    id: PerformanceComparisonId
    recommendation_id: RecommendationId
    baseline_id: PerformanceBaselineId
    comparison_window_days: int
    current_cost_micros: int
    current_clicks: int
    current_impressions: int
    current_conversions: float
    current_cpa_micros: int
    delta_cpa_pct: float
    delta_conversions_pct: float
    delta_ctr_pct: float
    verdict: Verdict
    compared_at: datetime

    @classmethod
    def create(
        cls,
        recommendation_id: RecommendationId,
        baseline: PerformanceBaseline,
        comparison_window_days: int,
        current_cost_micros: int,
        current_clicks: int,
        current_impressions: int,
        current_conversions: float,
        compared_at: datetime,
    ) -> PerformanceComparison:
        current_cpa_micros = int(current_cost_micros / current_conversions) if current_conversions > 0 else 0
        current_ctr = current_clicks / current_impressions if current_impressions > 0 else 0.0

        def _pct_change(new: float, old: float) -> float:
            if old == 0:
                return 0.0
            return (new - old) / old * 100.0

        delta_cpa_pct = _pct_change(current_cpa_micros, baseline.cpa_micros)
        delta_conversions_pct = _pct_change(current_conversions, baseline.conversions)
        delta_ctr_pct = _pct_change(current_ctr, baseline.ctr)

        # IMPROVED: CPA decreased >5% OR conversions increased >10%
        # DEGRADED: CPA increased >15% AND conversions didn't increase
        # NEUTRAL: otherwise
        if delta_cpa_pct < -5.0 or delta_conversions_pct > 10.0:
            verdict: Verdict = "IMPROVED"
        elif delta_cpa_pct > 15.0 and delta_conversions_pct <= 0:
            verdict = "DEGRADED"
        else:
            verdict = "NEUTRAL"

        return cls(
            id=str(uuid.uuid4()),
            recommendation_id=recommendation_id,
            baseline_id=baseline.id,
            comparison_window_days=comparison_window_days,
            current_cost_micros=current_cost_micros,
            current_clicks=current_clicks,
            current_impressions=current_impressions,
            current_conversions=current_conversions,
            current_cpa_micros=current_cpa_micros,
            delta_cpa_pct=delta_cpa_pct,
            delta_conversions_pct=delta_conversions_pct,
            delta_ctr_pct=delta_ctr_pct,
            verdict=verdict,
            compared_at=compared_at,
        )
