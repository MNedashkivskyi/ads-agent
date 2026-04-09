"""Unit tests for SendDailyDigestUseCase."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from adcopilot.application.use_cases.send_daily_digest import DigestResult, SendDailyDigestUseCase
from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)
from adcopilot.infrastructure.telegram.fake_notifier import FakeTelegramNotifier

_ACCOUNT_ID = AccountId("acct-1")
_USER_ID = UserId(str(uuid.uuid4()))
_TODAY = date(2026, 4, 10)
_CHAT_ID = 123456789


def _rec(
    kind: RecommendationKind = RecommendationKind.PAUSE_KEYWORD,
    severity: RecommendationSeverity = RecommendationSeverity.HIGH,
    savings_micros: int = 5_000_000,
    evidence: dict | None = None,
) -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=_ACCOUNT_ID,
        kind=kind,
        severity=severity,
        target={"ad_group_id": 1},
        payload={},
        evidence=evidence or {},
        estimated_monthly_savings_micros=savings_micros,
        created_at=datetime(2026, 4, 10, tzinfo=UTC),
        status=RecommendationStatus.PENDING,
    )


def _make_rec_repo(recs: list[Recommendation]) -> object:
    repo = AsyncMock()
    repo.list_pending = AsyncMock(return_value=recs)
    return repo


def _make_digest_log(already_sent: bool = False) -> object:
    repo = AsyncMock()
    repo.was_sent_today = AsyncMock(return_value=already_sent)
    repo.record = AsyncMock()
    return repo


def _make_uc(
    recs: list[Recommendation],
    already_sent: bool = False,
    notifier: FakeTelegramNotifier | None = None,
) -> tuple[SendDailyDigestUseCase, FakeTelegramNotifier]:
    notifier = notifier or FakeTelegramNotifier()
    uc = SendDailyDigestUseCase(
        account_repo=AsyncMock(),
        rec_repo=_make_rec_repo(recs),
        digest_log_repo=_make_digest_log(already_sent),
        notifier=notifier,
    )
    return uc, notifier


# ---------------------------------------------------------------------------
# no_telegram skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skips_when_no_telegram_chat_id() -> None:
    uc, notifier = _make_uc(recs=[_rec()])
    result = await uc.execute(
        user_id=_USER_ID, telegram_chat_id=None, account_ids=[_ACCOUNT_ID], today=_TODAY
    )
    assert result == DigestResult(sent=False, count=0, reason="no_telegram")
    assert len(notifier.calls) == 0


# ---------------------------------------------------------------------------
# all-clear suppression
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skips_when_no_pending_recommendations() -> None:
    uc, notifier = _make_uc(recs=[])
    result = await uc.execute(
        user_id=_USER_ID, telegram_chat_id=_CHAT_ID, account_ids=[_ACCOUNT_ID], today=_TODAY
    )
    assert result == DigestResult(sent=False, count=0, reason="no_recommendations")
    assert len(notifier.calls) == 0


# ---------------------------------------------------------------------------
# already sent today
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skips_when_already_sent_today() -> None:
    uc, notifier = _make_uc(recs=[_rec()], already_sent=True)
    result = await uc.execute(
        user_id=_USER_ID, telegram_chat_id=_CHAT_ID, account_ids=[_ACCOUNT_ID], today=_TODAY
    )
    assert result == DigestResult(sent=False, count=0, reason="already_sent")
    assert len(notifier.calls) == 0


# ---------------------------------------------------------------------------
# top-5 sort
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sends_top_5_when_more_available() -> None:
    recs = [_rec(savings_micros=i * 1_000_000) for i in range(10)]
    uc, notifier = _make_uc(recs=recs)
    result = await uc.execute(
        user_id=_USER_ID, telegram_chat_id=_CHAT_ID, account_ids=[_ACCOUNT_ID], today=_TODAY
    )
    assert result.sent is True
    assert result.count == 5
    assert len(notifier.calls) == 1
    assert len(notifier.calls[0]["recommendations"]) == 5


@pytest.mark.asyncio
async def test_sends_all_when_fewer_than_5() -> None:
    recs = [_rec() for _ in range(3)]
    uc, _notifier = _make_uc(recs=recs)
    result = await uc.execute(
        user_id=_USER_ID, telegram_chat_id=_CHAT_ID, account_ids=[_ACCOUNT_ID], today=_TODAY
    )
    assert result.sent is True
    assert result.count == 3


# ---------------------------------------------------------------------------
# severity ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critical_comes_before_low() -> None:
    low_rec = _rec(severity=RecommendationSeverity.LOW, savings_micros=100_000_000)
    critical_rec = _rec(severity=RecommendationSeverity.CRITICAL, savings_micros=1_000_000)
    uc, notifier = _make_uc(recs=[low_rec, critical_rec])
    await uc.execute(
        user_id=_USER_ID, telegram_chat_id=_CHAT_ID, account_ids=[_ACCOUNT_ID], today=_TODAY
    )
    sent_recs: list[Recommendation] = notifier.calls[0]["recommendations"]  # type: ignore[assignment]
    assert sent_recs[0].severity == RecommendationSeverity.CRITICAL
    assert sent_recs[1].severity == RecommendationSeverity.LOW


# ---------------------------------------------------------------------------
# digest log recorded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_records_digest_log_after_send() -> None:
    rec = _rec()
    notifier = FakeTelegramNotifier()
    digest_log = _make_digest_log(already_sent=False)
    uc = SendDailyDigestUseCase(
        account_repo=AsyncMock(),
        rec_repo=_make_rec_repo([rec]),
        digest_log_repo=digest_log,
        notifier=notifier,
    )
    await uc.execute(
        user_id=_USER_ID, telegram_chat_id=_CHAT_ID, account_ids=[_ACCOUNT_ID], today=_TODAY
    )
    digest_log.record.assert_awaited_once()
    call_args = digest_log.record.call_args
    assert call_args.args[0] == _USER_ID
    assert call_args.args[1] == _TODAY
    assert str(rec.id) in call_args.args[2]


# ---------------------------------------------------------------------------
# correct chat_id used
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sends_to_correct_chat_id() -> None:
    uc, notifier = _make_uc(recs=[_rec()])
    await uc.execute(
        user_id=_USER_ID, telegram_chat_id=_CHAT_ID, account_ids=[_ACCOUNT_ID], today=_TODAY
    )
    assert notifier.calls[0]["chat_id"] == _CHAT_ID
