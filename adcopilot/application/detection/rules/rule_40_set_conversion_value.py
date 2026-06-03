"""Rule 40 — Set Conversion Value.

Fires when an account records ≥ 10 conversions but `conv_value` is 0 across
all ENABLED campaigns.  Without conversion values Google cannot optimise for
ROAS, and the account owner cannot calculate true return on ad spend.

A single account-level recommendation is raised.
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
from adcopilot.domain.value_derivation import derive_conversion_value

_MIN_CONVERSIONS = 10.0


class SetConversionValueRule:
    kind = RecommendationKind.SET_CONVERSION_VALUE
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        enabled = [c for c in ctx.campaigns if c.status == "ENABLED"]
        if not enabled:
            return []

        total_conversions = sum(c.conversions for c in enabled)
        total_conv_value = sum(c.conv_value for c in enabled)

        if total_conversions < _MIN_CONVERSIONS:
            return []
        if total_conv_value > 0:
            return []

        # Executable only when business economics are configured — then we know
        # the value to apply. Without economics, the Measurement Health
        # diagnostic (value_tracking sub-score) nudges the user to configure it.
        econ = ctx.business_economics
        if econ is None or not econ.is_configured():
            return []

        # Apply a default value to each ENABLED primary conversion action whose
        # category yields a derivable value from the account's economics.
        recs: list[Recommendation] = []
        for action in ctx.conversion_actions:
            if action.status != "ENABLED" or not action.include_in_conversions_metric:
                continue
            value = derive_conversion_value(econ, category=action.category)
            if value is None or value <= 0:
                continue
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target={"conversion_action_id": action.conversion_action_id},
                    payload={
                        "conversion_action_id": action.conversion_action_id,
                        "value": value,
                        "currency_code": econ.currency_code,
                        "conversion_action_name": action.name,
                    },
                    evidence={
                        "conversion_action_name": action.name,
                        "category": action.category,
                        "derived_value": value,
                        "currency_code": econ.currency_code,
                        "total_conversions": total_conversions,
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )
        return recs
