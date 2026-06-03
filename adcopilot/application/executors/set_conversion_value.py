"""Executor: set a default conversion value on a conversion action.

Turns a SET_CONVERSION_VALUE recommendation (economics-derived value for a
specific conversion action) into a real Google Ads write so the account can
bid on value (tROAS).
"""

from __future__ import annotations

from typing import Any

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.domain.recommendation import Recommendation, RecommendationKind


class SetConversionValueExecutor:
    kind = RecommendationKind.SET_CONVERSION_VALUE

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        conversion_action_id = int(rec.payload["conversion_action_id"])
        value = float(rec.payload["value"])
        currency_code = str(rec.payload.get("currency_code", "PLN"))
        await mutations.set_conversion_action_value(
            refresh_token=refresh_token,
            customer_id=customer_id,
            conversion_action_id=conversion_action_id,
            value=value,
            currency_code=currency_code,
        )
        return {
            "conversion_action_id": conversion_action_id,
            "value": value,
            "currency_code": currency_code,
            "action": "conversion_value_set",
        }
