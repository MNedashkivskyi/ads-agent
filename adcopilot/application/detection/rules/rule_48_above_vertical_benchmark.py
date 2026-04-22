"""Rule 48 — CPA Above Vertical Benchmark.

Fires when the account's 30-day average CPA exceeds the vertical benchmark p75
by more than 50% (i.e. account_cpa > p75 * 1.5).  This flags accounts that are
significantly over-paying relative to their vertical peers.

No executor — purely informational advisory card.
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

_P75_MULTIPLIER = 1.5  # account CPA must exceed p75 * this factor to trigger


class AboveVerticalBenchmarkRule:
    """Fires when account CPA > vertical benchmark p75 × 1.5."""

    kind = RecommendationKind.ABOVE_VERTICAL_BENCHMARK
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        benchmark = ctx.vertical_benchmark
        if benchmark is None:
            return []

        account_cpa = ctx.history.avg_cpa_micros
        if account_cpa <= 0:
            return []

        p75 = benchmark.p75_cpa_micros
        if p75 <= 0:
            return []

        threshold = p75 * _P75_MULTIPLIER
        if account_cpa <= threshold:
            return []

        account_cpa_pln = account_cpa / 1_000_000
        p75_pln = p75 / 1_000_000
        median_pln = benchmark.median_cpa_micros / 1_000_000
        pct_above = round((account_cpa / p75 - 1) * 100, 1)

        return [
            Recommendation(
                id=RecommendationId(str(uuid.uuid4())),
                account_id=ctx.account.customer_id,
                kind=self.kind,
                severity=self.severity,
                status=RecommendationStatus.PENDING,
                target={"account_id": ctx.account.customer_id},
                payload={
                    "account_cpa_micros": account_cpa,
                    "account_cpa_pln": round(account_cpa_pln, 2),
                    "benchmark_p75_micros": p75,
                    "benchmark_p75_pln": round(p75_pln, 2),
                    "benchmark_median_pln": round(median_pln, 2),
                    "benchmark_account_count": benchmark.account_count,
                    "vertical": benchmark.vertical,
                    "city_tier": benchmark.city_tier,
                    "pct_above_p75": pct_above,
                },
                estimated_monthly_savings_micros=0,
                evidence={
                    "account_cpa_micros": account_cpa,
                    "benchmark_p75_micros": p75,
                    "pct_above_p75": pct_above,
                },
                created_at=datetime.now(UTC),
            )
        ]
