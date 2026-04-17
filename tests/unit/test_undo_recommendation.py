"""Unit tests for UndoRecommendationUseCase."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.application.use_cases.undo_recommendation import (
    UNDO_WINDOW_DAYS,
    UndoRecommendationUseCase,
)
from adcopilot.domain.audit_log import AuditLog, AuditLogId
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
_NOW = datetime.now()


def _rec(
    kind: RecommendationKind,
    status: RecommendationStatus = RecommendationStatus.EXECUTED,
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


def _audit_log(rec: Recommendation, created_at: datetime | None = None) -> AuditLog:
    return AuditLog(
        id=AuditLogId(str(uuid.uuid4())),
        recommendation_id=rec.id,
        account_id=rec.account_id,
        kind=rec.kind.value,
        action="EXECUTE",
        payload={"ad_group_id": 10, "criterion_id": 55, "action": "paused"},
        created_at=created_at or _NOW,
    )


def _make_uc(
    rec: Recommendation,
    audit_log: AuditLog | None,
    mutations: FakeGoogleAdsMutations | None = None,
) -> tuple[UndoRecommendationUseCase, FakeGoogleAdsMutations]:
    mutations = mutations or FakeGoogleAdsMutations()

    rec_repo = MagicMock()
    rec_repo.get = AsyncMock(return_value=rec)
    rec_repo.update_status = AsyncMock()

    audit_repo = MagicMock()
    audit_repo.get_latest_execute = AsyncMock(return_value=audit_log)
    audit_repo.save = AsyncMock()

    from adcopilot.domain.entities import GoogleAdsAccount, OAuthCredentials, UserId

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

    creds = OAuthCredentials(
        account_id=_ACCOUNT_ID,
        refresh_token=_REFRESH_TOKEN,
        access_token=None,
        expires_at=None,
    )
    creds_repo = MagicMock()
    creds_repo.get = AsyncMock(return_value=creds)

    uc = UndoRecommendationUseCase(
        rec_repo=rec_repo,
        audit_log_repo=audit_repo,
        account_repo=account_repo,
        credentials_repo=creds_repo,
        mutations=mutations,
    )
    return uc, mutations


# ---------------------------------------------------------------------------
# Guard conditions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_raises_if_not_found() -> None:
    rec = _rec(RecommendationKind.PAUSE_KEYWORD)
    uc, _ = _make_uc(rec, _audit_log(rec))
    uc._rec_repo.get = AsyncMock(return_value=None)
    with pytest.raises(ValueError, match="not found"):
        await uc.execute(RecommendationId(str(uuid.uuid4())))


@pytest.mark.asyncio
async def test_undo_raises_if_not_executed() -> None:
    rec = _rec(RecommendationKind.PAUSE_KEYWORD, status=RecommendationStatus.APPROVED)
    uc, _ = _make_uc(rec, _audit_log(rec))
    with pytest.raises(ValueError, match="not EXECUTED"):
        await uc.execute(rec.id)


@pytest.mark.asyncio
async def test_undo_raises_if_no_audit_log() -> None:
    rec = _rec(RecommendationKind.PAUSE_KEYWORD)
    uc, _ = _make_uc(rec, audit_log=None)
    with pytest.raises(ValueError, match="No EXECUTE audit log"):
        await uc.execute(rec.id)


@pytest.mark.asyncio
async def test_undo_raises_if_window_expired() -> None:
    rec = _rec(RecommendationKind.PAUSE_KEYWORD)
    old_log = _audit_log(rec, created_at=_NOW - timedelta(days=UNDO_WINDOW_DAYS + 1))
    uc, _ = _make_uc(rec, old_log)
    with pytest.raises(ValueError, match="window expired"):
        await uc.execute(rec.id)


# ---------------------------------------------------------------------------
# PAUSE_KEYWORD undo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_pause_keyword_calls_enable_keyword() -> None:
    rec = _rec(RecommendationKind.PAUSE_KEYWORD)
    log = AuditLog(
        id=AuditLogId(str(uuid.uuid4())),
        recommendation_id=rec.id,
        account_id=rec.account_id,
        kind=rec.kind.value,
        action="EXECUTE",
        payload={"ad_group_id": 10, "criterion_id": 55, "action": "paused"},
        created_at=_NOW,
    )
    uc, mutations = _make_uc(rec, log)
    result = await uc.execute(rec.id)
    assert mutations.calls[0]["method"] == "enable_keyword"
    assert mutations.calls[0]["criterion_id"] == 55
    assert result["action"] == "enabled"


# ---------------------------------------------------------------------------
# PAUSE_AD undo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_pause_ad_calls_enable_ad() -> None:
    rec = _rec(RecommendationKind.PAUSE_AD)
    log = AuditLog(
        id=AuditLogId(str(uuid.uuid4())),
        recommendation_id=rec.id,
        account_id=rec.account_id,
        kind=rec.kind.value,
        action="EXECUTE",
        payload={"ad_group_id": 5, "ad_id": 42, "action": "paused"},
        created_at=_NOW,
    )
    uc, mutations = _make_uc(rec, log)
    result = await uc.execute(rec.id)
    assert mutations.calls[0]["method"] == "enable_ad"
    assert mutations.calls[0]["ad_id"] == 42
    assert result["action"] == "enabled"


# ---------------------------------------------------------------------------
# ADD_NEGATIVE_KEYWORD undo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_add_negative_keyword_calls_remove() -> None:
    rec = _rec(RecommendationKind.ADD_NEGATIVE_KEYWORD)
    log = AuditLog(
        id=AuditLogId(str(uuid.uuid4())),
        recommendation_id=rec.id,
        account_id=rec.account_id,
        kind=rec.kind.value,
        action="EXECUTE",
        payload={
            "ad_group_id": 7,
            "keyword_text": "free stuff",
            "match_type": "EXACT",
            "action": "added_negative",
        },
        created_at=_NOW,
    )
    uc, mutations = _make_uc(rec, log)
    result = await uc.execute(rec.id)
    assert mutations.calls[0]["method"] == "remove_ad_group_negative_keyword"
    assert mutations.calls[0]["keyword_text"] == "free stuff"
    assert result["action"] == "negative_removed"


# ---------------------------------------------------------------------------
# INCREASE_BUDGET undo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_increase_budget_restores_old_budget() -> None:
    rec = _rec(
        RecommendationKind.INCREASE_BUDGET,
        payload={"campaign_id": 200, "current_budget_micros": 5_000_000, "suggested_budget_micros": 6_000_000},
    )
    log = AuditLog(
        id=AuditLogId(str(uuid.uuid4())),
        recommendation_id=rec.id,
        account_id=rec.account_id,
        kind=rec.kind.value,
        action="EXECUTE",
        payload={"campaign_id": 200, "new_budget_micros": 6_000_000, "action": "budget_increased"},
        created_at=_NOW,
    )
    uc, mutations = _make_uc(rec, log)
    result = await uc.execute(rec.id)
    assert mutations.calls[0]["method"] == "update_campaign_budget"
    assert mutations.calls[0]["new_budget_micros"] == 5_000_000
    assert result["action"] == "budget_restored"


# ---------------------------------------------------------------------------
# State transitions and audit log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_resets_status_to_approved() -> None:
    rec = _rec(RecommendationKind.PAUSE_KEYWORD)
    log = AuditLog(
        id=AuditLogId(str(uuid.uuid4())),
        recommendation_id=rec.id,
        account_id=rec.account_id,
        kind=rec.kind.value,
        action="EXECUTE",
        payload={"ad_group_id": 1, "criterion_id": 1, "action": "paused"},
        created_at=_NOW,
    )
    uc, _ = _make_uc(rec, log)
    await uc.execute(rec.id)
    uc._rec_repo.update_status.assert_awaited_once_with(rec.id, RecommendationStatus.APPROVED)


@pytest.mark.asyncio
async def test_undo_saves_undo_audit_log() -> None:
    rec = _rec(RecommendationKind.PAUSE_KEYWORD)
    log = AuditLog(
        id=AuditLogId(str(uuid.uuid4())),
        recommendation_id=rec.id,
        account_id=rec.account_id,
        kind=rec.kind.value,
        action="EXECUTE",
        payload={"ad_group_id": 1, "criterion_id": 1, "action": "paused"},
        created_at=_NOW,
    )
    uc, _ = _make_uc(rec, log)
    await uc.execute(rec.id)
    uc._audit_log_repo.save.assert_awaited_once()
    saved_log = uc._audit_log_repo.save.call_args.args[0]
    assert saved_log.action == "UNDO"
    assert saved_log.kind == RecommendationKind.PAUSE_KEYWORD.value


# ---------------------------------------------------------------------------
# CHANGE_MATCH_TYPE undo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_change_match_type_restores_old_match_type() -> None:
    rec = _rec(
        RecommendationKind.CHANGE_MATCH_TYPE,
        payload={
            "criterion_id": 77,
            "ad_group_id": 20,
            "current_match_type": "BROAD",
            "suggested_match_type": "PHRASE",
        },
    )
    log = AuditLog(
        id=AuditLogId(str(uuid.uuid4())),
        recommendation_id=rec.id,
        account_id=rec.account_id,
        kind=rec.kind.value,
        action="EXECUTE",
        payload={
            "ad_group_id": 20,
            "criterion_id": 77,
            "old_match_type": "BROAD",
            "new_match_type": "PHRASE",
            "action": "match_type_changed",
        },
        created_at=_NOW,
    )
    uc, mutations = _make_uc(rec, log)
    result = await uc.execute(rec.id)
    assert mutations.calls[0]["method"] == "change_keyword_match_type"
    assert mutations.calls[0]["criterion_id"] == 77
    assert mutations.calls[0]["match_type"] == "BROAD"
    assert result["action"] == "match_type_restored"
    assert result["restored_match_type"] == "BROAD"


# ---------------------------------------------------------------------------
# ADJUST_BIDDING_STRATEGY undo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_adjust_bidding_strategy_restores_old_strategy() -> None:
    rec = _rec(
        RecommendationKind.ADJUST_BIDDING_STRATEGY,
        payload={
            "campaign_id": 500,
            "current_strategy": "MAXIMIZE_CLICKS",
            "suggested_strategy": "MAXIMIZE_CONVERSIONS",
        },
    )
    log = AuditLog(
        id=AuditLogId(str(uuid.uuid4())),
        recommendation_id=rec.id,
        account_id=rec.account_id,
        kind=rec.kind.value,
        action="EXECUTE",
        payload={
            "campaign_id": 500,
            "old_strategy": "MAXIMIZE_CLICKS",
            "new_strategy": "MAXIMIZE_CONVERSIONS",
            "action": "bidding_strategy_changed",
        },
        created_at=_NOW,
    )
    uc, mutations = _make_uc(rec, log)
    result = await uc.execute(rec.id)
    assert mutations.calls[0]["method"] == "set_campaign_bidding_strategy"
    assert mutations.calls[0]["campaign_id"] == 500
    assert mutations.calls[0]["bidding_strategy"] == "MAXIMIZE_CLICKS"
    assert result["action"] == "bidding_strategy_restored"
    assert result["restored_strategy"] == "MAXIMIZE_CLICKS"


# ---------------------------------------------------------------------------
# ADJUST_BUDGET undo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_adjust_budget_restores_old_budget() -> None:
    rec = _rec(
        RecommendationKind.ADJUST_BUDGET,
        payload={
            "campaign_id": 300,
            "current_budget_micros": 4_000_000,
            "new_budget_micros": 3_000_000,
        },
    )
    log = AuditLog(
        id=AuditLogId(str(uuid.uuid4())),
        recommendation_id=rec.id,
        account_id=rec.account_id,
        kind=rec.kind.value,
        action="EXECUTE",
        payload={
            "campaign_id": 300,
            "new_budget_micros": 3_000_000,
            "action": "budget_adjusted",
        },
        created_at=_NOW,
    )
    uc, mutations = _make_uc(rec, log)
    result = await uc.execute(rec.id)
    assert mutations.calls[0]["method"] == "update_campaign_budget"
    assert mutations.calls[0]["campaign_id"] == 300
    assert mutations.calls[0]["new_budget_micros"] == 4_000_000
    assert result["action"] == "budget_restored"
    assert result["restored_budget_micros"] == 4_000_000
