"""Executor: move 20% of donor campaign budget to a constrained receiver campaign."""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind

_TRANSFER_RATIO = 0.20
_MIN_REMAINING_MICROS = 1_000_000  # 1 PLN minimum


class ReallocateBudgetExecutor:
    kind = RecommendationKind.REALLOCATE_BUDGET

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        from_campaign_id = int(rec.target["from_campaign_id"])
        to_campaign_id = int(rec.target["to_campaign_id"])
        donor_budget_micros = int(rec.evidence["donor_budget_micros"])
        receiver_budget_micros = int(rec.evidence["receiver_budget_micros"])

        transfer_micros = int(donor_budget_micros * _TRANSFER_RATIO)
        new_donor_budget = donor_budget_micros - transfer_micros
        new_receiver_budget = receiver_budget_micros + transfer_micros

        if new_donor_budget < _MIN_REMAINING_MICROS:
            raise ValueError(
                f"Donor budget too low: {donor_budget_micros} micros, "
                f"transfer {transfer_micros} would leave {new_donor_budget} < {_MIN_REMAINING_MICROS}"
            )

        await mutations.update_campaign_budget(
            refresh_token=refresh_token,
            customer_id=customer_id,
            campaign_id=from_campaign_id,
            new_budget_micros=new_donor_budget,
        )
        await mutations.update_campaign_budget(
            refresh_token=refresh_token,
            customer_id=customer_id,
            campaign_id=to_campaign_id,
            new_budget_micros=new_receiver_budget,
        )
        return {
            "from_campaign_id": from_campaign_id,
            "to_campaign_id": to_campaign_id,
            "transfer_micros": transfer_micros,
            "old_donor_budget_micros": donor_budget_micros,
            "new_donor_budget_micros": new_donor_budget,
            "old_receiver_budget_micros": receiver_budget_micros,
            "new_receiver_budget_micros": new_receiver_budget,
            "action": "budget_reallocated",
        }
