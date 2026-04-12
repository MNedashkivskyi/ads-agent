"""Detection rule: ad group contains more than 15 enabled keywords (overstuffed)."""

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

# Ad groups with more than this many enabled keywords are too broad and
# hurt relevance scores. Google recommends 10-20 tightly themed keywords.
_MAX_KEYWORDS = 15


class OverstuffedAdGroupRule:
    kind = RecommendationKind.OVERSTUFFED_AD_GROUP
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        # Build a lookup for ad group names and campaign_ids
        ag_info: dict[int, tuple[str, int]] = {
            ag.ad_group_id: (ag.name, ag.campaign_id) for ag in ctx.ad_groups
        }

        # Count enabled keywords per ad group
        enabled_counts: dict[int, int] = {}
        for kw in ctx.keywords:
            if kw.status == "ENABLED":
                enabled_counts[kw.ad_group_id] = enabled_counts.get(kw.ad_group_id, 0) + 1

        recs: list[Recommendation] = []
        for ad_group_id, count in enabled_counts.items():
            if count <= _MAX_KEYWORDS:
                continue

            ag_name, campaign_id = ag_info.get(ad_group_id, ("", 0))
            target = {"ad_group_id": ad_group_id, "campaign_id": campaign_id}
            evidence = {
                "ad_group_name": ag_name,
                "keyword_count": count,
                "enabled_keywords": count,
                "threshold": _MAX_KEYWORDS,
            }
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target=target,
                    payload={"ad_group_id": ad_group_id, "campaign_id": campaign_id},
                    evidence=evidence,
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
