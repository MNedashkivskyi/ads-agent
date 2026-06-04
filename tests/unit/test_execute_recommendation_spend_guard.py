"""Execution-path tests for the preventive spend guardrail (SS1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.application.use_cases.execute_recommendation import ExecuteRecommendationUseCase
from adcopilot.domain.entities import AccountId, GoogleAdsAccount, OAuthCredentials, UserId
from adcopilot.domain.exceptions import SpendGuardViolation
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)
from adcopilot.domain.spend_guard import AccountSpendContext
from adcopilot.domain.spend_safety import SpendSafetyConfig
from adcopilot.infrastructure.google_ads.fake_mutations import FakeGoogleAdsMutations

_ACCOUNT_ID = AccountId("acct-1")
_NOW = datetime(2026, 4, 10, tzinfo=UTC)


def _budget_rec(current: int, new: int) -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=_ACCOUNT_ID,
        kind=RecommendationKind.INCREASE_BUDGET,
        severity=RecommendationSeverity.HIGH,
        target={},
        payload={
            "campaign_id": 555,
            "current_budget_micros": current,
            "suggested_budget_micros": new,
        },
        evidence={},
        estimated_monthly_savings_micros=0,
        created_at=_NOW,
        status=RecommendationStatus.APPROVED,
    )


def _use_case(rec: Recommendation, config: SpendSafetyConfig, ctx: AccountSpendContext):
    mutations = FakeGoogleAdsMutations()
    rec_repo = MagicMock()
    rec_repo.get = AsyncMock(return_value=rec)
    rec_repo.update_status = AsyncMock()
    audit_repo = MagicMock()
    audit_repo.save = AsyncMock()

    account = GoogleAdsAccount(
        id=_ACCOUNT_ID,
        user_id=UserId("user-1"),
        customer_id="123-456-7890",
        descriptive_name="Test",
        currency="PLN",
        timezone="UTC",
        is_manager=False,
        write_enabled=True,
        connected_at=_NOW,
    )
    account_repo = MagicMock()
    account_repo.get = AsyncMock(return_value=account)
    creds_repo = MagicMock()
    creds_repo.get = AsyncMock(
        return_value=OAuthCredentials(
            account_id=_ACCOUNT_ID, refresh_token="tok", access_token=None, expires_at=None
        )
    )
    ss_repo = MagicMock()
    ss_repo.get = AsyncMock(return_value=config)

    async def provider(_account_id: str) -> AccountSpendContext:
        return ctx

    uc = ExecuteRecommendationUseCase(
        rec_repo=rec_repo,
        audit_log_repo=audit_repo,
        account_repo=account_repo,
        credentials_repo=creds_repo,
        mutations=mutations,
        spend_safety_repo=ss_repo,
        account_spend_provider=provider,
    )
    return uc, mutations, rec_repo


@pytest.mark.asyncio
async def test_violating_budget_raise_is_blocked() -> None:
    config = SpendSafetyConfig(
        account_id="acct-1", monthly_spend_cap_micros=10_000_000_000, max_budget_increase_pct=50.0
    )
    ctx = AccountSpendContext(month_to_date_spend_micros=0, days_elapsed=15, days_in_month=30)
    # +300% raise -> exceeds 50% single-action cap
    uc, mutations, rec_repo = _use_case(_budget_rec(1_000_000, 4_000_000), config, ctx)

    with pytest.raises(SpendGuardViolation) as exc:
        await uc.execute(RecommendationId("x"))

    assert exc.value.code == "MAX_BUDGET_INCREASE"
    assert mutations.calls == []  # mutation never executed
    rec_repo.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_within_cap_budget_raise_executes() -> None:
    config = SpendSafetyConfig(
        account_id="acct-1", monthly_spend_cap_micros=10_000_000_000, max_budget_increase_pct=50.0
    )
    ctx = AccountSpendContext(month_to_date_spend_micros=100_000_000, days_elapsed=15, days_in_month=30)
    uc, mutations, rec_repo = _use_case(_budget_rec(1_000_000, 1_200_000), config, ctx)  # +20%

    await uc.execute(RecommendationId("x"))

    assert any(c["method"] == "update_campaign_budget" for c in mutations.calls)
    rec_repo.update_status.assert_called_once()


@pytest.mark.asyncio
async def test_no_config_does_not_block() -> None:
    config = SpendSafetyConfig(account_id="acct-1")  # no caps -> guard inert
    ctx = AccountSpendContext()
    uc, mutations, _ = _use_case(_budget_rec(1_000_000, 100_000_000), config, ctx)

    await uc.execute(RecommendationId("x"))

    assert any(c["method"] == "update_campaign_budget" for c in mutations.calls)
