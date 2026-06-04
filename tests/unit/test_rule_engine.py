"""Unit tests for RuleEngine and RunDetectionUseCase."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.application.detection.base import DetectionContext, HistoricalStats
from adcopilot.application.detection.engine import RuleEngine
from adcopilot.domain.entities import AccountId, GoogleAdsAccount, UserId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ACCOUNT_ID = AccountId(str(uuid.uuid4()))
_SNAP_DATE = date(2026, 4, 9)
_NOW = datetime(2026, 4, 9, tzinfo=UTC)


def _make_account() -> GoogleAdsAccount:
    return GoogleAdsAccount(
        id=_ACCOUNT_ID,
        user_id=UserId("user-1"),
        customer_id="123456789",
        descriptive_name="Test Account",
        currency="EUR",
        timezone="Europe/Berlin",
        is_manager=False,
        write_enabled=True,
        connected_at=_NOW,
    )


def _make_ctx() -> DetectionContext:
    return DetectionContext(
        account=_make_account(),
        campaigns=[],
        ad_groups=[],
        keywords=[],
        search_terms=[],
        ads=[],
        history=HistoricalStats(avg_cpa_micros=0, total_cost_micros=0, total_conversions=0.0),
        snapshot_date=_SNAP_DATE,
    )


def _make_rec(kind: RecommendationKind = RecommendationKind.PAUSE_KEYWORD) -> Recommendation:
    target: dict[str, Any] = {"criterion_id": int(uuid.uuid4().int % 100000)}
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=_ACCOUNT_ID,
        kind=kind,
        severity=RecommendationSeverity.HIGH,
        target=target,
        payload={},
        evidence={},
        estimated_monthly_savings_micros=1_000_000,
        created_at=_NOW,
        status=RecommendationStatus.PENDING,
    )


class _EmptyRule:
    kind = RecommendationKind.PAUSE_KEYWORD

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        return []


class _OneRecRule:
    kind = RecommendationKind.PAUSE_KEYWORD

    def __init__(self, rec: Recommendation | None = None) -> None:
        self._rec = rec or _make_rec()

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        return [self._rec]


# ---------------------------------------------------------------------------
# RuleEngine tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_empty_rules_returns_empty() -> None:
    """Engine with no rules produces no recommendations."""
    repo = MagicMock()
    repo.list_active_dedup_keys = AsyncMock(return_value=set())
    repo.save = AsyncMock()

    engine = RuleEngine(rules=[], rec_repo=repo)
    result = await engine.run(_make_ctx())

    assert result == []
    repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_engine_empty_rule_does_not_save() -> None:
    """A rule that returns empty list causes no saves."""
    repo = MagicMock()
    repo.list_active_dedup_keys = AsyncMock(return_value=set())
    repo.save = AsyncMock()

    engine = RuleEngine(rules=[_EmptyRule()], rec_repo=repo)
    result = await engine.run(_make_ctx())

    assert result == []
    repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_engine_one_rec_rule_saves_and_returns() -> None:
    """A rule returning one recommendation causes one save."""
    rec = _make_rec()
    repo = MagicMock()
    repo.list_active_dedup_keys = AsyncMock(return_value=set())
    repo.save = AsyncMock()

    engine = RuleEngine(rules=[_OneRecRule(rec)], rec_repo=repo)
    result = await engine.run(_make_ctx())

    assert result == [rec]
    repo.save.assert_awaited_once_with(rec)


@pytest.mark.asyncio
async def test_engine_reconciles_stale_pending_when_campaigns_present() -> None:
    """When real campaign data exists, the engine expires PENDING recs that the
    current run no longer detects, keeping only currently-actual candidate keys."""
    rec = _make_rec()
    repo = MagicMock()
    repo.list_active_dedup_keys = AsyncMock(return_value=set())
    repo.save = AsyncMock()
    repo.expire_pending_not_matching = AsyncMock(return_value=3)

    ctx = _make_ctx()
    object.__setattr__(ctx, "campaigns", [MagicMock()])  # non-empty → reconcile

    engine = RuleEngine(rules=[_OneRecRule(rec)], rec_repo=repo)
    await engine.run(ctx)

    repo.expire_pending_not_matching.assert_awaited_once()
    _account_id, keep_keys = repo.expire_pending_not_matching.await_args.args
    assert (rec.kind.value, rec.target_hash) in keep_keys


@pytest.mark.asyncio
async def test_engine_skips_reconcile_when_no_campaign_data() -> None:
    """An empty/failed snapshot (no campaigns) must not expire anything."""
    repo = MagicMock()
    repo.list_active_dedup_keys = AsyncMock(return_value=set())
    repo.save = AsyncMock()
    repo.expire_pending_not_matching = AsyncMock(return_value=0)

    engine = RuleEngine(rules=[_EmptyRule()], rec_repo=repo)
    await engine.run(_make_ctx())  # campaigns=[]

    repo.expire_pending_not_matching.assert_not_called()


@pytest.mark.asyncio
async def test_engine_dedup_skips_existing_pending() -> None:
    """If (kind, target_hash) already exists, engine skips the new rec."""
    rec = _make_rec()
    repo = MagicMock()
    # Return the rec's dedup key as already present
    repo.list_active_dedup_keys = AsyncMock(return_value={(rec.kind, rec.target_hash)})
    repo.save = AsyncMock()

    engine = RuleEngine(rules=[_OneRecRule(rec)], rec_repo=repo)
    result = await engine.run(_make_ctx())

    assert result == []
    repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_engine_dedup_same_batch_skips_second_duplicate() -> None:
    """Two rules returning the same (kind, target_hash) — only first is saved."""
    rec = _make_rec()
    # second rule returns a new Recommendation object but same kind+target_hash
    rec2 = Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=rec.account_id,
        kind=rec.kind,
        severity=rec.severity,
        target=rec.target,  # same target → same hash
        payload={},
        evidence={},
        estimated_monthly_savings_micros=0,
        created_at=_NOW,
        status=RecommendationStatus.PENDING,
    )
    repo = MagicMock()
    repo.list_active_dedup_keys = AsyncMock(return_value=set())
    repo.save = AsyncMock()

    engine = RuleEngine(rules=[_OneRecRule(rec), _OneRecRule(rec2)], rec_repo=repo)
    result = await engine.run(_make_ctx())

    assert len(result) == 1
    assert repo.save.await_count == 1


@pytest.mark.asyncio
async def test_engine_rule_raising_exception_is_skipped() -> None:
    """A rule that raises does not crash the engine; other rules still run."""

    class _BrokenRule:
        kind = RecommendationKind.PAUSE_KEYWORD

        def detect(self, ctx: DetectionContext) -> list[Recommendation]:
            raise RuntimeError("oops")

    good_rec = _make_rec()
    repo = MagicMock()
    repo.list_active_dedup_keys = AsyncMock(return_value=set())
    repo.save = AsyncMock()

    engine = RuleEngine(rules=[_BrokenRule(), _OneRecRule(good_rec)], rec_repo=repo)
    result = await engine.run(_make_ctx())

    assert result == [good_rec]


# ---------------------------------------------------------------------------
# RunDetectionUseCase tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_detection_returns_counts_by_severity() -> None:
    """Use case aggregates recommendations by severity."""
    from adcopilot.application.ports.snapshot_repository import SnapshotData
    from adcopilot.application.use_cases.run_detection import RunDetectionUseCase

    account = _make_account()
    account_repo = MagicMock()
    account_repo.get = AsyncMock(return_value=account)

    snapshot_repo = MagicMock()
    snapshot_repo.load_snapshot = AsyncMock(
        return_value=SnapshotData(campaigns=[], ad_groups=[], keywords=[], search_terms=[], ads=[])
    )

    critical_rec = Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=_ACCOUNT_ID,
        kind=RecommendationKind.FIX_DISAPPROVED_AD,
        severity=RecommendationSeverity.CRITICAL,
        target={"ad_id": 1},
        payload={},
        evidence={},
        estimated_monthly_savings_micros=0,
        created_at=_NOW,
        status=RecommendationStatus.PENDING,
    )
    high_rec = _make_rec(RecommendationKind.ADD_NEGATIVE_KEYWORD)

    rec_repo = MagicMock()
    engine = MagicMock()
    engine.run = AsyncMock(return_value=[critical_rec, high_rec])

    use_case = RunDetectionUseCase(
        snapshot_repo=snapshot_repo,
        rec_repo=rec_repo,
        rule_engine=engine,
        account_repo=account_repo,
    )
    counts = await use_case.execute(_ACCOUNT_ID, _SNAP_DATE)

    assert counts["CRITICAL"] == 1
    assert counts["HIGH"] == 1
    assert counts["MEDIUM"] == 0
    assert counts["LOW"] == 0


@pytest.mark.asyncio
async def test_run_detection_account_not_found_returns_empty() -> None:
    """If account is not found, returns empty dict without crashing."""
    from adcopilot.application.use_cases.run_detection import RunDetectionUseCase

    account_repo = MagicMock()
    account_repo.get = AsyncMock(return_value=None)

    use_case = RunDetectionUseCase(
        snapshot_repo=MagicMock(),
        rec_repo=MagicMock(),
        rule_engine=MagicMock(),
        account_repo=account_repo,
    )
    result = await use_case.execute(_ACCOUNT_ID, _SNAP_DATE)

    assert result == {}


@pytest.mark.asyncio
async def test_run_detection_threads_spend_safety_config_into_context() -> None:
    """Spend-safety config from the repo is wired into the DetectionContext."""
    from adcopilot.application.ports.snapshot_repository import SnapshotData
    from adcopilot.application.use_cases.run_detection import RunDetectionUseCase
    from adcopilot.domain.spend_safety import SpendSafetyConfig

    account = _make_account()
    account_repo = MagicMock()
    account_repo.get = AsyncMock(return_value=account)

    snapshot_repo = MagicMock()
    snapshot_repo.load_snapshot = AsyncMock(
        return_value=SnapshotData(campaigns=[], ad_groups=[], keywords=[], search_terms=[], ads=[])
    )

    config = SpendSafetyConfig(account_id=str(_ACCOUNT_ID), monthly_spend_cap_micros=5_000_000_000)
    ss_repo = MagicMock()
    ss_repo.get = AsyncMock(return_value=config)

    engine = MagicMock()
    engine.run = AsyncMock(return_value=[])

    use_case = RunDetectionUseCase(
        snapshot_repo=snapshot_repo,
        rec_repo=MagicMock(),
        rule_engine=engine,
        account_repo=account_repo,
        spend_safety_repo=ss_repo,
    )
    await use_case.execute(_ACCOUNT_ID, _SNAP_DATE)

    ctx = engine.run.call_args.args[0]
    assert ctx.spend_safety_config is config
    assert ctx.spend_safety_config.monthly_spend_cap_micros == 5_000_000_000
