"""Unit tests for AdCopyRefreshExecutor."""

from __future__ import annotations

import json
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.application.executors.refresh_ad_copy import AdCopyRefreshExecutor
from adcopilot.domain.ad_copy_proposal import AdCopyProposal
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_SAMPLE_JSON = json.dumps([
    {"headlines": ["H1", "H2", "H3"], "descriptions": ["D1", "D2"]},
    {"headlines": ["H4", "H5", "H6"], "descriptions": ["D3", "D4"]},
    {"headlines": ["H7", "H8", "H9"], "descriptions": ["D5", "D6"]},
])


def _make_rec(evidence: dict) -> Recommendation:
    return Recommendation(
        id=RecommendationId("rec-1"),
        account_id=AccountId("acc-1"),
        kind=RecommendationKind.AD_FATIGUE,
        severity=RecommendationSeverity.MEDIUM,
        target={"account_id": "acc-1", "ad_group_id": "42"},
        payload={},
        evidence=evidence,
        estimated_monthly_savings_micros=0,
        created_at=datetime.now(UTC),
        status=RecommendationStatus.PENDING,
    )


def _make_executor() -> tuple[AdCopyRefreshExecutor, AsyncMock, AsyncMock]:
    llm = AsyncMock()
    llm.complete.return_value = _SAMPLE_JSON
    prompt_repo = AsyncMock()
    pv = MagicMock()
    pv.content = "{campaign_name} {vertical} {keyword_themes} {existing_headlines} {existing_descriptions}"
    prompt_repo.get_latest.return_value = pv
    executor = AdCopyRefreshExecutor(llm=llm, prompt_repo=prompt_repo)
    return executor, llm, prompt_repo


@pytest.mark.asyncio
async def test_execute_creates_three_rsas() -> None:
    executor, _, _ = _make_executor()
    mutations = AsyncMock()
    mutations.create_rsa.side_effect = [101, 102, 103]

    rec = _make_rec({"ad_group_id": 42, "final_url": "https://x.com"})
    result = await executor.execute(rec, mutations, "token", "123")

    assert mutations.create_rsa.call_count == 3
    assert result["created_ad_ids"] == [101, 102, 103]


@pytest.mark.asyncio
async def test_execute_enables_new_ads() -> None:
    executor, _, _ = _make_executor()
    mutations = AsyncMock()
    mutations.create_rsa.side_effect = [101, 102, 103]

    rec = _make_rec({"ad_group_id": 42, "final_url": "https://x.com"})
    await executor.execute(rec, mutations, "token", "123")

    assert mutations.enable_ad.call_count == 3


@pytest.mark.asyncio
async def test_execute_pauses_lowest_ctr_ad() -> None:
    executor, _, _ = _make_executor()
    mutations = AsyncMock()
    mutations.create_rsa.side_effect = [101, 102, 103]

    rec = _make_rec({"ad_group_id": 42, "final_url": "https://x.com", "lowest_ctr_ad_id": 99})
    result = await executor.execute(rec, mutations, "token", "123")

    mutations.pause_ad.assert_called_once_with(
        refresh_token="token", customer_id="123", ad_group_id=42, ad_id=99
    )
    assert result["paused_ad_id"] == 99


@pytest.mark.asyncio
async def test_execute_skips_pause_when_no_lowest_ctr_ad() -> None:
    executor, _, _ = _make_executor()
    mutations = AsyncMock()
    mutations.create_rsa.side_effect = [101, 102, 103]

    rec = _make_rec({"ad_group_id": 42, "final_url": "https://x.com"})
    result = await executor.execute(rec, mutations, "token", "123")

    mutations.pause_ad.assert_not_called()
    assert result["paused_ad_id"] is None


@pytest.mark.asyncio
async def test_undo_pauses_new_ads_and_re_enables_old() -> None:
    from adcopilot.application.use_cases.undo_recommendation import UndoRecommendationUseCase
    from adcopilot.domain.audit_log import AuditLog, AuditLogId
    from adcopilot.domain.recommendation import RecommendationStatus

    mutations = AsyncMock()
    audit_log_repo = AsyncMock()
    rec_repo = AsyncMock()
    credentials_repo = AsyncMock()
    account_repo = AsyncMock()

    # Must be EXECUTED status for undo to proceed
    rec = Recommendation(
        id=RecommendationId("rec-1"),
        account_id=AccountId("acc-1"),
        kind=RecommendationKind.AD_FATIGUE,
        severity=RecommendationSeverity.MEDIUM,
        target={"account_id": "acc-1", "ad_group_id": "42"},
        payload={},
        evidence={"ad_group_id": 42},
        estimated_monthly_savings_micros=0,
        created_at=datetime.now(UTC),
        status=RecommendationStatus.EXECUTED,
    )
    rec_repo.get.return_value = rec
    rec_repo.update_status = AsyncMock()

    audit_log = AuditLog(
        id=AuditLogId("log-1"),
        recommendation_id=rec.id,
        account_id=rec.account_id,
        kind="EXECUTE",
        action="EXECUTE",
        payload={
            "ad_group_id": 42,
            "created_ad_ids": [101, 102, 103],
            "paused_ad_id": 99,
            "action": "ad_copy_refreshed",
        },
        created_at=datetime.now(UTC),
    )
    audit_log_repo.get_latest_execute.return_value = audit_log
    audit_log_repo.save = AsyncMock()

    creds = MagicMock()
    creds.refresh_token = "token"
    credentials_repo.get.return_value = creds

    account = MagicMock()
    account.customer_id = "123"
    account.user_id = "user-1"
    account_repo.get.return_value = account

    undo_uc = UndoRecommendationUseCase(
        rec_repo=rec_repo,
        audit_log_repo=audit_log_repo,
        mutations=mutations,
        credentials_repo=credentials_repo,
        account_repo=account_repo,
    )
    result = await undo_uc.execute(rec.id)

    # Should pause all 3 new ads
    assert mutations.pause_ad.call_count == 3
    # Should re-enable the original paused ad
    mutations.enable_ad.assert_called_once_with(
        refresh_token="token", customer_id="123", ad_group_id=42, ad_id=99
    )
    assert result["action"] == "ad_copy_refresh_undone"
