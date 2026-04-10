"""Unit tests for Task 6.2 — Telegram conversation flow."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adcopilot.application.use_cases.send_daily_digest import DigestResult, SendDailyDigestUseCase
from adcopilot.domain.entities import AccountId, PlanTier, User, UserId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)
from adcopilot.infrastructure.telegram.callback_handler import _format_evidence
from adcopilot.infrastructure.telegram.fake_notifier import FakeTelegramNotifier

_ACCOUNT_ID = AccountId("acct-test-1")
_USER_ID = UserId(str(uuid.uuid4()))
_TODAY = date(2026, 4, 10)
_CHAT_ID = 999_888_777


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_user(paused: bool = False) -> User:
    return User(
        id=_USER_ID,
        email="test@example.com",
        telegram_chat_id=_CHAT_ID,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        plan=PlanTier.STARTER,
        notifications_paused=paused,
    )


def _make_rec(savings: int = 5_000_000) -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=_ACCOUNT_ID,
        kind=RecommendationKind.PAUSE_KEYWORD,
        severity=RecommendationSeverity.HIGH,
        target={"ad_group_id": 1},
        payload={},
        evidence={"impressions": 100, "clicks": 0, "cost_micros": 500_000},
        estimated_monthly_savings_micros=savings,
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
# digest skips paused users
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_digest_skips_paused_user() -> None:
    uc, notifier = _make_uc(recs=[_make_rec()])
    result = await uc.execute(
        user_id=_USER_ID,
        telegram_chat_id=_CHAT_ID,
        account_ids=[_ACCOUNT_ID],
        today=_TODAY,
        notifications_paused=True,
    )
    assert result == DigestResult(sent=False, count=0, reason="paused")
    assert len(notifier.calls) == 0


@pytest.mark.asyncio
async def test_digest_sends_when_not_paused() -> None:
    uc, notifier = _make_uc(recs=[_make_rec()])
    result = await uc.execute(
        user_id=_USER_ID,
        telegram_chat_id=_CHAT_ID,
        account_ids=[_ACCOUNT_ID],
        today=_TODAY,
        notifications_paused=False,
    )
    assert result.sent is True
    assert len(notifier.calls) == 1


# ---------------------------------------------------------------------------
# notifications_paused field on User entity
# ---------------------------------------------------------------------------


def test_user_notifications_paused_defaults_false() -> None:
    user = _make_user(paused=False)
    assert user.notifications_paused is False


def test_user_notifications_paused_can_be_true() -> None:
    user = _make_user(paused=True)
    assert user.notifications_paused is True


# ---------------------------------------------------------------------------
# _format_evidence (more: callback helper)
# ---------------------------------------------------------------------------


def test_format_evidence_empty() -> None:
    result = _format_evidence({})
    assert result == "Brak szczegółowych danych."


def test_format_evidence_formats_keys_and_values() -> None:
    evidence = {"impressions": 1500, "cost_micros": 2_000_000, "click_rate": 0.10}
    result = _format_evidence(evidence)
    assert "• Impressions: 1500" in result
    assert "• Cost micros: 2000000" in result
    assert "• Click rate: 0.10" in result


def test_format_evidence_replaces_underscores() -> None:
    evidence = {"search_term": "buy shoes"}
    result = _format_evidence(evidence)
    assert "• Search term: buy shoes" in result


# ---------------------------------------------------------------------------
# fallback_handler sends correct message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_handler_replies_with_help_hint() -> None:
    from adcopilot.infrastructure.telegram.handlers import fallback_handler

    update = MagicMock()
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await fallback_handler(update, context)

    update.message.reply_text.assert_awaited_once()
    call_text: str = update.message.reply_text.call_args[0][0]
    assert "/help" in call_text


# ---------------------------------------------------------------------------
# pause_handler / resume_handler set notifications_paused correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_handler_sets_paused_true() -> None:
    from adcopilot.infrastructure.telegram.handlers import pause_handler

    update = MagicMock()
    update.message = AsyncMock()
    update.message.chat_id = _CHAT_ID
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    saved_users: list[User] = []

    mock_user_model = MagicMock()
    mock_user_model.id = uuid.UUID(_USER_ID)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none = MagicMock(return_value=mock_user_model)
    mock_session.execute.return_value = scalar_result

    mock_repo = AsyncMock()
    mock_repo.get_by_id = AsyncMock(return_value=_make_user(paused=False))
    mock_repo.save = AsyncMock(side_effect=lambda u: saved_users.append(u))

    with (
        patch(
            "adcopilot.infrastructure.telegram.handlers.create_async_engine",
            return_value=MagicMock(dispose=AsyncMock()),
        ),
        patch(
            "adcopilot.infrastructure.telegram.handlers.AsyncSession",
            return_value=mock_session,
        ),
        patch(
            "adcopilot.infrastructure.telegram.handlers.SqlUserRepository",
            return_value=mock_repo,
        ),
    ):
        await pause_handler(update, context)

    assert len(saved_users) == 1
    assert saved_users[0].notifications_paused is True


@pytest.mark.asyncio
async def test_resume_handler_sets_paused_false() -> None:
    from adcopilot.infrastructure.telegram.handlers import resume_handler

    update = MagicMock()
    update.message = AsyncMock()
    update.message.chat_id = _CHAT_ID
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    saved_users: list[User] = []

    mock_user_model = MagicMock()
    mock_user_model.id = uuid.UUID(_USER_ID)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none = MagicMock(return_value=mock_user_model)
    mock_session.execute.return_value = scalar_result

    mock_repo = AsyncMock()
    mock_repo.get_by_id = AsyncMock(return_value=_make_user(paused=True))
    mock_repo.save = AsyncMock(side_effect=lambda u: saved_users.append(u))

    with (
        patch(
            "adcopilot.infrastructure.telegram.handlers.create_async_engine",
            return_value=MagicMock(dispose=AsyncMock()),
        ),
        patch(
            "adcopilot.infrastructure.telegram.handlers.AsyncSession",
            return_value=mock_session,
        ),
        patch(
            "adcopilot.infrastructure.telegram.handlers.SqlUserRepository",
            return_value=mock_repo,
        ),
    ):
        await resume_handler(update, context)

    assert len(saved_users) == 1
    assert saved_users[0].notifications_paused is False
