"""Rule 39 — Deduplicate Conversions.

Fires when the account's `all_conversions` (which includes view-through and
cross-device) exceeds the reported `conversions` by more than 5×.  A ratio
this large almost always indicates double-counting — typically caused by
having both a Google tag AND an imported GA4 goal that track the same event.

One account-level recommendation is raised when:
  - Total all_conversions across ENABLED campaigns > 0
  - Total conversions > 0
  - all_conversions / conversions > 5.0
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

_DUPLICATION_RATIO_THRESHOLD = 5.0


class DeduplicateConversionsRule:
    kind = RecommendationKind.DEDUPLICATE_CONVERSIONS
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        enabled = [c for c in ctx.campaigns if c.status == "ENABLED"]
        if not enabled:
            return []

        total_conversions = sum(c.conversions for c in enabled)
        total_all_conversions = sum(c.all_conversions for c in enabled)

        if total_conversions <= 0 or total_all_conversions <= 0:
            return []

        ratio = total_all_conversions / total_conversions
        if ratio <= _DUPLICATION_RATIO_THRESHOLD:
            return []

        return [
            Recommendation(
                id=RecommendationId(str(uuid.uuid4())),
                account_id=ctx.account.id,  # type: ignore[arg-type]
                kind=self.kind,
                severity=self.severity,
                target={"account_id": str(ctx.account.id)},
                payload={"account_id": str(ctx.account.id)},
                evidence={
                    "total_conversions": total_conversions,
                    "total_all_conversions": total_all_conversions,
                    "ratio": round(ratio, 2),
                    "threshold": _DUPLICATION_RATIO_THRESHOLD,
                },
                estimated_monthly_savings_micros=0,
                created_at=datetime.now(tz=UTC),
                status=RecommendationStatus.PENDING,
            )
        ]
