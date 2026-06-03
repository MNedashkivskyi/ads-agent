from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adcopilot.application.executors.set_conversion_value import SetConversionValueExecutor
from adcopilot.domain.recommendation import (
    NON_EXECUTABLE_KINDS,
    Recommendation,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)


class FakeMutations:
    def __init__(self):
        self.calls = []

    async def set_conversion_action_value(
        self, *, refresh_token, customer_id, conversion_action_id, value, currency_code
    ):
        self.calls.append(
            {
                "conversion_action_id": conversion_action_id,
                "value": value,
                "currency_code": currency_code,
                "customer_id": customer_id,
            }
        )


def _rec() -> Recommendation:
    return Recommendation(
        id="r1",
        account_id="a1",
        kind=RecommendationKind.SET_CONVERSION_VALUE,
        severity=RecommendationSeverity.MEDIUM,
        target={"conversion_action_id": 99},
        payload={"conversion_action_id": 99, "value": 60.0, "currency_code": "PLN"},
        estimated_monthly_savings_micros=0,
        evidence={},
        created_at=datetime.now(UTC),
        status=RecommendationStatus.APPROVED,
    )


def test_set_conversion_value_is_executable() -> None:
    assert RecommendationKind.SET_CONVERSION_VALUE not in NON_EXECUTABLE_KINDS


@pytest.mark.asyncio
async def test_executor_calls_mutation_with_payload() -> None:
    mutations = FakeMutations()
    result = await SetConversionValueExecutor().execute(
        _rec(), mutations, refresh_token="rt", customer_id="123-456-7890"
    )
    assert mutations.calls == [
        {
            "conversion_action_id": 99,
            "value": 60.0,
            "currency_code": "PLN",
            "customer_id": "123-456-7890",
        }
    ]
    assert result["action"] == "conversion_value_set"
