"""Unit tests for ExecuteRecommendationUseCase and individual executors."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.application.executors.add_negative_keyword import AddNegativeKeywordExecutor
from adcopilot.application.executors.adjust_bidding_strategy import AdjustBiddingStrategyExecutor
from adcopilot.application.executors.adjust_budget import AdjustBudgetExecutor
from adcopilot.application.executors.change_match_type import ChangeMatchTypeExecutor
from adcopilot.application.executors.increase_budget import IncreaseBudgetExecutor
from adcopilot.application.executors.pause_ad import PauseAdExecutor
from adcopilot.application.executors.pause_keyword import PauseKeywordExecutor
from adcopilot.application.use_cases.execute_recommendation import ExecuteRecommendationUseCase
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)
from adcopilot.infrastructure.google_ads.fake_mutations import FakeGoogleAdsMutations

_ACCOUNT_ID = AccountId("acct-1")
_CUSTOMER_ID = "123-456-7890"
_REFRESH_TOKEN = "tok"
_NOW = datetime(2026, 4, 10, tzinfo=UTC)


def _rec(
    kind: RecommendationKind,
    status: RecommendationStatus = RecommendationStatus.APPROVED,
    target: dict | None = None,
    payload: dict | None = None,
) -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=_ACCOUNT_ID,
        kind=kind,
        severity=RecommendationSeverity.HIGH,
        target=target or {},
        payload=payload or {},
        evidence={},
        estimated_monthly_savings_micros=5_000_000,
        created_at=_NOW,
        status=status,
    )


def _make_use_case(
    rec: Recommendation,
    mutations: FakeGoogleAdsMutations | None = None,
) -> tuple[ExecuteRecommendationUseCase, FakeGoogleAdsMutations]:
    mutations = mutations or FakeGoogleAdsMutations()
    rec_repo = MagicMock()
    rec_repo.get = AsyncMock(return_value=rec)
    rec_repo.update_status = AsyncMock()

    audit_repo = MagicMock()
    audit_repo.save = AsyncMock()

    from adcopilot.domain.entities import GoogleAdsAccount, UserId

    account = GoogleAdsAccount(
        id=_ACCOUNT_ID,
        user_id=UserId("user-1"),
        customer_id=_CUSTOMER_ID,
        descriptive_name="Test",
        currency="EUR",
        timezone="UTC",
        is_manager=False,
        write_enabled=True,
        connected_at=_NOW,
    )
    account_repo = MagicMock()
    account_repo.get = AsyncMock(return_value=account)

    from adcopilot.domain.entities import OAuthCredentials

    creds = OAuthCredentials(
        account_id=_ACCOUNT_ID,
        refresh_token=_REFRESH_TOKEN,
        access_token=None,
        expires_at=None,
    )
    creds_repo = MagicMock()
    creds_repo.get = AsyncMock(return_value=creds)

    uc = ExecuteRecommendationUseCase(
        rec_repo=rec_repo,
        audit_log_repo=audit_repo,
        account_repo=account_repo,
        credentials_repo=creds_repo,
        mutations=mutations,
    )
    return uc, mutations


# ---------------------------------------------------------------------------
# PauseKeywordExecutor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_keyword_executor_calls_mutation() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        RecommendationKind.PAUSE_KEYWORD,
        target={"ad_group_id": 10, "criterion_id": 99},
    )
    executor = PauseKeywordExecutor()
    result = await executor.execute(rec, mutations, _REFRESH_TOKEN, _CUSTOMER_ID)
    assert len(mutations.calls) == 1
    call = mutations.calls[0]
    assert call["method"] == "pause_keyword"
    assert call["ad_group_id"] == 10
    assert call["criterion_id"] == 99
    assert result["action"] == "paused"


# ---------------------------------------------------------------------------
# PauseAdExecutor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_ad_executor_calls_mutation() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(RecommendationKind.PAUSE_AD, target={"ad_group_id": 5, "ad_id": 42})
    executor = PauseAdExecutor()
    result = await executor.execute(rec, mutations, _REFRESH_TOKEN, _CUSTOMER_ID)
    assert mutations.calls[0]["method"] == "pause_ad"
    assert mutations.calls[0]["ad_id"] == 42
    assert result["action"] == "paused"


# ---------------------------------------------------------------------------
# AddNegativeKeywordExecutor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_negative_keyword_executor_calls_mutation() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        RecommendationKind.ADD_NEGATIVE_KEYWORD,
        target={"ad_group_id": 7, "search_term": "free stuff"},
        payload={"negative_keyword": "free stuff", "match_type": "EXACT"},
    )
    executor = AddNegativeKeywordExecutor()
    result = await executor.execute(rec, mutations, _REFRESH_TOKEN, _CUSTOMER_ID)
    assert mutations.calls[0]["method"] == "add_ad_group_negative_keyword"
    assert mutations.calls[0]["keyword_text"] == "free stuff"
    assert mutations.calls[0]["match_type"] == "EXACT"
    assert result["action"] == "added_negative"


# ---------------------------------------------------------------------------
# IncreaseBudgetExecutor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_increase_budget_executor_calls_mutation() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        RecommendationKind.INCREASE_BUDGET,
        payload={
            "campaign_id": 200,
            "current_budget_micros": 5_000_000,
            "suggested_budget_micros": 6_000_000,
        },
    )
    executor = IncreaseBudgetExecutor()
    result = await executor.execute(rec, mutations, _REFRESH_TOKEN, _CUSTOMER_ID)
    assert mutations.calls[0]["method"] == "update_campaign_budget"
    assert mutations.calls[0]["new_budget_micros"] == 6_000_000
    assert result["action"] == "budget_increased"


# ---------------------------------------------------------------------------
# ExecuteRecommendationUseCase — orchestration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_use_case_updates_status_to_executed() -> None:
    rec = _rec(
        RecommendationKind.PAUSE_KEYWORD,
        target={"ad_group_id": 10, "criterion_id": 99},
    )
    uc, _ = _make_use_case(rec)
    await uc.execute(rec.id)
    uc._rec_repo.update_status.assert_awaited_once_with(rec.id, RecommendationStatus.EXECUTED)


@pytest.mark.asyncio
async def test_execute_use_case_saves_audit_log() -> None:
    rec = _rec(
        RecommendationKind.PAUSE_KEYWORD,
        target={"ad_group_id": 10, "criterion_id": 99},
    )
    uc, _ = _make_use_case(rec)
    await uc.execute(rec.id)
    uc._audit_log_repo.save.assert_awaited_once()
    log = uc._audit_log_repo.save.call_args.args[0]
    assert log.action == "EXECUTE"
    assert log.kind == RecommendationKind.PAUSE_KEYWORD.value


@pytest.mark.asyncio
async def test_execute_raises_if_not_approved() -> None:
    rec = _rec(
        RecommendationKind.PAUSE_KEYWORD,
        status=RecommendationStatus.PENDING,
        target={"ad_group_id": 1, "criterion_id": 1},
    )
    uc, _ = _make_use_case(rec)
    with pytest.raises(ValueError, match="not APPROVED"):
        await uc.execute(rec.id)


@pytest.mark.asyncio
async def test_execute_raises_if_not_found() -> None:
    rec = _rec(RecommendationKind.PAUSE_KEYWORD)
    uc, _ = _make_use_case(rec)
    uc._rec_repo.get = AsyncMock(return_value=None)
    with pytest.raises(ValueError, match="not found"):
        await uc.execute(RecommendationId(str(uuid.uuid4())))


@pytest.mark.asyncio
async def test_execute_raises_for_non_automatable_kind() -> None:
    rec = _rec(RecommendationKind.ENABLE_CONVERSION_TRACKING)
    uc, _ = _make_use_case(rec)
    with pytest.raises(ValueError, match="No executor"):
        await uc.execute(rec.id)


@pytest.mark.asyncio
async def test_execute_calls_mutation_and_returns_result() -> None:
    rec = _rec(
        RecommendationKind.PAUSE_KEYWORD,
        target={"ad_group_id": 10, "criterion_id": 55},
    )
    uc, mutations = _make_use_case(rec)
    result = await uc.execute(rec.id)
    assert len(mutations.calls) == 1
    assert result["criterion_id"] == 55


# ---------------------------------------------------------------------------
# ChangeMatchTypeExecutor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_match_type_executor_calls_mutation() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        RecommendationKind.CHANGE_MATCH_TYPE,
        payload={
            "ad_group_id": 20,
            "criterion_id": 77,
            "current_match_type": "BROAD",
            "suggested_match_type": "PHRASE",
        },
    )
    executor = ChangeMatchTypeExecutor()
    result = await executor.execute(rec, mutations, _REFRESH_TOKEN, _CUSTOMER_ID)
    assert len(mutations.calls) == 1
    call = mutations.calls[0]
    assert call["method"] == "change_keyword_match_type"
    assert call["ad_group_id"] == 20
    assert call["criterion_id"] == 77
    assert call["match_type"] == "PHRASE"
    assert result["old_match_type"] == "BROAD"
    assert result["new_match_type"] == "PHRASE"
    assert result["action"] == "match_type_changed"


# ---------------------------------------------------------------------------
# AdjustBiddingStrategyExecutor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adjust_bidding_strategy_executor_calls_mutation() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        RecommendationKind.ADJUST_BIDDING_STRATEGY,
        payload={
            "campaign_id": 500,
            "current_strategy": "MAXIMIZE_CLICKS",
            "suggested_strategy": "MAXIMIZE_CONVERSIONS",
        },
    )
    executor = AdjustBiddingStrategyExecutor()
    result = await executor.execute(rec, mutations, _REFRESH_TOKEN, _CUSTOMER_ID)
    assert len(mutations.calls) == 1
    call = mutations.calls[0]
    assert call["method"] == "set_campaign_bidding_strategy"
    assert call["campaign_id"] == 500
    assert call["bidding_strategy"] == "MAXIMIZE_CONVERSIONS"
    assert result["old_strategy"] == "MAXIMIZE_CLICKS"
    assert result["new_strategy"] == "MAXIMIZE_CONVERSIONS"
    assert result["action"] == "bidding_strategy_changed"


# ---------------------------------------------------------------------------
# AdjustBudgetExecutor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adjust_budget_executor_calls_mutation() -> None:
    mutations = FakeGoogleAdsMutations()
    rec = _rec(
        RecommendationKind.ADJUST_BUDGET,
        payload={
            "campaign_id": 300,
            "current_budget_micros": 4_000_000,
            "new_budget_micros": 3_000_000,
        },
    )
    executor = AdjustBudgetExecutor()
    result = await executor.execute(rec, mutations, _REFRESH_TOKEN, _CUSTOMER_ID)
    assert len(mutations.calls) == 1
    call = mutations.calls[0]
    assert call["method"] == "update_campaign_budget"
    assert call["campaign_id"] == 300
    assert call["new_budget_micros"] == 3_000_000
    assert result["action"] == "budget_adjusted"
