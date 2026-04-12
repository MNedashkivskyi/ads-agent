"""Rule 38 — Upgrade Conversion Action.

Fires when ALL active, included conversion actions for an account have
micro-conversion categories (PAGE_VIEW, DEFAULT, UNKNOWN, or any name that
looks like a button click / scroll event).

Real purchase/lead conversions provide accurate optimisation signals to
Smart Bidding.  Tracking only soft engagement events leads Google to
optimise for vanity metrics rather than business outcomes.

Detection heuristic (no LLM needed):
  - Category == PAGE_VIEW → definitely micro
  - Category == DEFAULT → catch-all, usually micro
  - Name contains any of the micro-signal keywords below → likely micro
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

# Categories that are definitively micro-conversions.
_MICRO_CATEGORIES = {"PAGE_VIEW", "DEFAULT", "UNKNOWN"}

# Name substrings that indicate micro-conversion events (case-insensitive).
_MICRO_NAME_SIGNALS = {
    "scroll",
    "click",
    "button",
    "view",
    "visit",
    "session",
    "bounce",
    "engagement",
    "time on",
}

# Categories that are definitely macro-conversions — skip if any exist.
_MACRO_CATEGORIES = {"PURCHASE", "LEAD", "SIGNUP", "PHONE_CALL", "IMPORTED_LEAD", "QUALIFIED_LEAD"}


def _is_micro(action) -> bool:
    if action.category in _MACRO_CATEGORIES:
        return False
    if action.category in _MICRO_CATEGORIES:
        return True
    name_lower = action.name.lower()
    return any(signal in name_lower for signal in _MICRO_NAME_SIGNALS)


class UpgradeConversionActionRule:
    kind = RecommendationKind.UPGRADE_CONVERSION_ACTION
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.conversion_actions:
            return []

        # Only consider ENABLED actions that count toward Conversions column.
        active = [
            a for a in ctx.conversion_actions
            if a.status == "ENABLED" and a.include_in_conversions_metric
        ]
        if not active:
            return []

        # If any macro-conversion exists → account already tracks real outcomes.
        if any(a.category in _MACRO_CATEGORIES for a in active):
            return []

        # All active included actions are micro → fire one account-level rec.
        micro_names = [a.name for a in active if _is_micro(a)]
        if not micro_names:
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
                    "micro_conversion_names": micro_names,
                    "micro_conversion_count": len(micro_names),
                    "total_active_actions": len(active),
                },
                estimated_monthly_savings_micros=0,
                created_at=datetime.now(tz=UTC),
                status=RecommendationStatus.PENDING,
            )
        ]
