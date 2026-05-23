"""Tests for Approve/Decline/Snooze use cases and RuleEngine snooze check."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.application.detection.engine import RuleEngine
from adcopilot.application.use_cases.approve_recommendation import ApproveRecommendationUseCase
from adcopilot.application.use_cases.decline_recommendation import DeclineRecommendationUseCase
from adcopilot.application.use_cases.snooze_recommendation import SnoozeRecommendationUseCase
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_ACCOUNT_ID = AccountId("acct-1")
_NOW = datetime(2026, 4, 10, tzinfo=UTC)


def _rec(
    kind: RecommendationKind = RecommendationKind.PAUSE_KEYWORD,
    target: dict | None = None,
) -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=_ACCOUNT_ID,
        kind=kind,
        severity=RecommendationSeverity.HIGH,
        target=target or {"keyword_id": 1},
        payload={},
        evidence={},
        estimated_monthly_savings_micros=5_000_000,
        created_at=_NOW,
        status=RecommendationStatus.PENDING,
    )


def _rec_repo(rec: Recommendation | None) -> MagicMock:
    repo = MagicMock()
    repo.get = AsyncMock(return_value=rec)
    repo.update_status = AsyncMock()
    repo.list_pending = AsyncMock(return_value=[])
    repo.save = AsyncMock()
    return repo


def _snooze_repo(active_keys: set[tuple[str, str]] | None = None) -> MagicMock:
    repo = MagicMock()
    repo.save_snooze = AsyncMock()
    repo.get_active_snooze_keys = AsyncMock(return_value=active_keys or set())
    return repo


# ---------------------------------------------------------------------------
# ApproveRecommendationUseCase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_updates_status_to_approved() -> None:
    rec = _rec()
    repo = _rec_repo(rec)
    await ApproveRecommendationUseCase(repo).execute(rec.id)
    repo.update_status.assert_awaited_once_with(rec.id, RecommendationStatus.APPROVED)


@pytest.mark.asyncio
async def test_approve_raises_if_not_found() -> None:
    repo = _rec_repo(None)
    with pytest.raises(ValueError, match="not found"):
        await ApproveRecommendationUseCase(repo).execute(RecommendationId(str(uuid.uuid4())))


# ---------------------------------------------------------------------------
# DeclineRecommendationUseCase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decline_updates_status_to_declined() -> None:
    rec = _rec()
    repo = _rec_repo(rec)
    await DeclineRecommendationUseCase(repo).execute(rec.id)
    repo.update_status.assert_awaited_once_with(rec.id, RecommendationStatus.DECLINED)


@pytest.mark.asyncio
async def test_decline_raises_if_not_found() -> None:
    repo = _rec_repo(None)
    with pytest.raises(ValueError, match="not found"):
        await DeclineRecommendationUseCase(repo).execute(RecommendationId(str(uuid.uuid4())))


# ---------------------------------------------------------------------------
# SnoozeRecommendationUseCase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snooze_saves_snooze_record() -> None:
    rec = _rec()
    rec_repo = _rec_repo(rec)
    snooze = _snooze_repo()
    result = await SnoozeRecommendationUseCase(rec_repo, snooze).execute(rec.id)
    snooze.save_snooze.assert_awaited_once()
    args = snooze.save_snooze.call_args
    assert args.args[0] is rec
    # snoozed_until should be ~7 days from now
    snoozed_until = args.args[1]
    assert isinstance(snoozed_until, datetime)
    assert snoozed_until > datetime.now(UTC) + timedelta(days=6)
    assert result == snoozed_until


@pytest.mark.asyncio
async def test_snooze_raises_if_not_found() -> None:
    repo = _rec_repo(None)
    snooze = _snooze_repo()
    with pytest.raises(ValueError, match="not found"):
        await SnoozeRecommendationUseCase(repo, snooze).execute(RecommendationId(str(uuid.uuid4())))


@pytest.mark.asyncio
async def test_snooze_custom_days() -> None:
    rec = _rec()
    rec_repo = _rec_repo(rec)
    snooze = _snooze_repo()
    result = await SnoozeRecommendationUseCase(rec_repo, snooze).execute(rec.id, snooze_days=3)
    snoozed_until = snooze.save_snooze.call_args.args[1]
    assert result == snoozed_until
    assert snoozed_until < datetime.now(UTC) + timedelta(days=5)


# ---------------------------------------------------------------------------
# RuleEngine — snooze check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rule_engine_skips_snoozed_recommendation() -> None:
    rec = _rec(kind=RecommendationKind.PAUSE_KEYWORD, target={"keyword_id": 42})
    snoozed_keys = {(rec.kind.value, rec.target_hash)}

    mock_rule = MagicMock()
    mock_rule.detect = MagicMock(return_value=[rec])

    rec_repo = _rec_repo(rec)
    snooze = _snooze_repo(active_keys=snoozed_keys)

    from adcopilot.application.detection.base import DetectionContext

    ctx = MagicMock(spec=DetectionContext)
    ctx.account = MagicMock()
    ctx.account.id = _ACCOUNT_ID

    engine = RuleEngine(rules=[mock_rule], rec_repo=rec_repo, snooze_repo=snooze)
    new_recs = await engine.run(ctx)

    assert new_recs == []
    rec_repo.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_rule_engine_persists_non_snoozed_recommendation() -> None:
    rec = _rec(kind=RecommendationKind.PAUSE_KEYWORD, target={"keyword_id": 99})

    mock_rule = MagicMock()
    mock_rule.detect = MagicMock(return_value=[rec])

    rec_repo = _rec_repo(rec)
    snooze = _snooze_repo(active_keys=set())  # no active snoozes

    from adcopilot.application.detection.base import DetectionContext

    ctx = MagicMock(spec=DetectionContext)
    ctx.account = MagicMock()
    ctx.account.id = _ACCOUNT_ID

    engine = RuleEngine(rules=[mock_rule], rec_repo=rec_repo, snooze_repo=snooze)
    new_recs = await engine.run(ctx)

    assert len(new_recs) == 1
    rec_repo.save.assert_awaited_once_with(rec)


@pytest.mark.asyncio
async def test_rule_engine_without_snooze_repo_still_works() -> None:
    rec = _rec()
    mock_rule = MagicMock()
    mock_rule.detect = MagicMock(return_value=[rec])
    rec_repo = _rec_repo(rec)

    from adcopilot.application.detection.base import DetectionContext

    ctx = MagicMock(spec=DetectionContext)
    ctx.account = MagicMock()
    ctx.account.id = _ACCOUNT_ID

    engine = RuleEngine(rules=[mock_rule], rec_repo=rec_repo, snooze_repo=None)
    new_recs = await engine.run(ctx)

    assert len(new_recs) == 1
