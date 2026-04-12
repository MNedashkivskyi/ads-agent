"""Rule 33 — Reallocate Budget.

Fires when Campaign A has a ROAS ≥ 3.0 and is budget-constrained (spending
≥ 95% of its budget) while Campaign B has a ROAS < 1.0 and is underspending
(< 50% of budget).  Suggests moving budget FROM B TO A within the same
account to improve overall return.

One recommendation is raised per high-performing constrained campaign,
referencing the worst underspending campaign as the donor.
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

_MIN_ROAS_HIGH = 3.0          # campaign A must have ROAS ≥ this
_MAX_ROAS_LOW = 1.0           # campaign B must have ROAS < this
_BUDGET_UTILISATION_HIGH = 0.95   # constrained: spending ≥ 95% of budget
_BUDGET_UTILISATION_LOW = 0.50    # underspending: spending < 50% of budget
_MIN_SPEND_MICROS = 10_000_000   # minimum weekly spend (€10) to be meaningful


def _roas(campaign) -> float:
    cost_eur = campaign.cost_micros / 1_000_000
    return campaign.conv_value / cost_eur if cost_eur > 0 else 0.0


def _utilisation(campaign) -> float:
    return campaign.cost_micros / campaign.budget_micros if campaign.budget_micros > 0 else 0.0


class ReallocateBudgetRule:
    kind = RecommendationKind.REALLOCATE_BUDGET
    severity = RecommendationSeverity.CRITICAL

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        enabled = [c for c in ctx.campaigns if c.status == "ENABLED"]
        if len(enabled) < 2:
            return []

        # Split into high-performers (constrained) and low-performers (underspending).
        # The minimum spend threshold only applies to the high-ROAS receiver — we want
        # to confirm it is genuinely active before recommending more budget.
        high: list = []
        low: list = []
        for c in enabled:
            roas = _roas(c)
            util = _utilisation(c)
            if (
                roas >= _MIN_ROAS_HIGH
                and util >= _BUDGET_UTILISATION_HIGH
                and c.cost_micros >= _MIN_SPEND_MICROS
            ):
                high.append(c)
            elif roas < _MAX_ROAS_LOW and util < _BUDGET_UTILISATION_LOW:
                low.append(c)

        if not high or not low:
            return []

        # Pick the single worst underspending donor (lowest ROAS).
        donor = min(low, key=_roas)

        recs: list[Recommendation] = []
        for receiver in high:
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target={
                        "from_campaign_id": donor.campaign_id,
                        "to_campaign_id": receiver.campaign_id,
                    },
                    payload={
                        "from_campaign_id": donor.campaign_id,
                        "to_campaign_id": receiver.campaign_id,
                    },
                    evidence={
                        "receiver_campaign_name": receiver.name,
                        "receiver_roas": round(_roas(receiver), 2),
                        "receiver_budget_utilisation": round(_utilisation(receiver), 2),
                        "receiver_cost_micros": receiver.cost_micros,
                        "receiver_budget_micros": receiver.budget_micros,
                        "donor_campaign_name": donor.name,
                        "donor_roas": round(_roas(donor), 2),
                        "donor_budget_utilisation": round(_utilisation(donor), 2),
                        "donor_cost_micros": donor.cost_micros,
                        "donor_budget_micros": donor.budget_micros,
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
