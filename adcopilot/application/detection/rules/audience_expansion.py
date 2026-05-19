"""Detection rule: suggest audience expansion when impression share is saturated (>90%)."""

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

_IMPRESSION_SHARE_THRESHOLD = 0.90
_MIN_IMPRESSIONS = 500


class AudienceExpansionRule:
    kind = RecommendationKind.AUDIENCE_EXPANSION
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.audience_performance:
            return []

        # Build campaign impression share from campaign snapshots
        campaign_impression_share: dict[int, float] = {}
        for c in ctx.campaigns:
            if c.search_impression_share is not None:
                campaign_impression_share[c.campaign_id] = c.search_impression_share

        recs: list[Recommendation] = []
        seen_campaigns: set[int] = set()

        for aud in ctx.audience_performance:
            if aud.campaign_id in seen_campaigns:
                continue
            if aud.impressions < _MIN_IMPRESSIONS:
                continue

            is_val = campaign_impression_share.get(aud.campaign_id)
            if is_val is None or is_val < _IMPRESSION_SHARE_THRESHOLD:
                continue

            seen_campaigns.add(aud.campaign_id)
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=aud.account_id,
                    kind=self.kind,
                    severity=self.severity,
                    status=RecommendationStatus.PENDING,
                    title=f"Rozszerz grupę odbiorców w kampanii {aud.campaign_id}",
                    description=(
                        f"Udział w wyświetleniach kampanii {aud.campaign_id} przekroczył "
                        f"{is_val:.0%}. Istniejące grupy odbiorców są bliskie nasycenia — "
                        f"rozważ dodanie podobnych grup odbiorców (similar audiences) lub "
                        f"rozszerzenie targetowania na pokrewne zainteresowania."
                    ),
                    created_at=datetime.now(UTC),
                    metadata={
                        "campaign_id": aud.campaign_id,
                        "impression_share": round(is_val, 4),
                        "audience_impressions": aud.impressions,
                    },
                )
            )

        return recs
