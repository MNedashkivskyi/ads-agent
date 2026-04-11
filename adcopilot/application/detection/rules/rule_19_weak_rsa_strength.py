"""Detection rule: RSA ads with poor Google-reported ad strength or too few
unique headlines to allow effective machine-learning rotation.

Google's ad strength score ('POOR', 'AVERAGE', 'GOOD', 'EXCELLENT') directly
predicts how well the algorithm can optimise the ad.  Low-strength RSAs also
get fewer impressions.

We also flag RSAs with fewer than 8 unique headline slots — the recommended
minimum for the algorithm to find good combinations.
"""

from __future__ import annotations

import json
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

_RSA_TYPE = "RESPONSIVE_SEARCH_AD"
_MIN_IMPRESSIONS = 100
_WEAK_STRENGTHS = {"POOR", "AVERAGE"}
_MIN_HEADLINES = 8


class WeakRsaStrengthRule:
    kind = RecommendationKind.WEAK_RSA_STRENGTH
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        for ad in ctx.ads:
            if ad.status != "ENABLED":
                continue
            if _RSA_TYPE not in ad.type.upper():
                continue
            if ad.impressions < _MIN_IMPRESSIONS:
                continue

            try:
                headlines: list[str] = json.loads(ad.headlines_json)
            except (json.JSONDecodeError, TypeError):
                headlines = []

            unique_headlines = len(set(h.strip().lower() for h in headlines if h.strip()))
            strength_weak = ad.ad_strength in _WEAK_STRENGTHS
            too_few_headlines = unique_headlines < _MIN_HEADLINES

            if not (strength_weak or too_few_headlines):
                continue

            reason = []
            if strength_weak:
                reason.append(f"ad_strength={ad.ad_strength}")
            if too_few_headlines:
                reason.append(f"only {unique_headlines} unique headlines (min {_MIN_HEADLINES})")

            target = {"ad_id": ad.ad_id, "ad_group_id": ad.ad_group_id}
            payload = {"ad_id": ad.ad_id, "ad_group_id": ad.ad_group_id}
            evidence = {
                "ad_id": ad.ad_id,
                "ad_strength": ad.ad_strength,
                "unique_headlines": unique_headlines,
                "impressions": ad.impressions,
                "reason": ", ".join(reason),
            }
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
