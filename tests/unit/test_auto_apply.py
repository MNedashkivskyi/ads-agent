"""Unit tests for auto-apply domain logic + use case (Phase 3 / T3.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from adcopilot.application.use_cases.auto_apply import AutoApplyUseCase
from adcopilot.domain.auto_apply import (
    AutoApplyRisk,
    AutoApplySettings,
    is_auto_appliable,
    parse_risk,
    select_for_auto_apply,
)
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)


def _rec(kind: RecommendationKind, severity=RecommendationSeverity.MEDIUM, rid="r") -> Recommendation:
    return Recommendation(
        id=RecommendationId(rid),
        account_id=AccountId("acc-1"),
        kind=kind,
        severity=severity,
        target={"account_id": "acc-1"},
        payload={},
        evidence={},
        estimated_monthly_savings_micros=0,
        created_at=datetime.now(UTC),
        status=RecommendationStatus.PENDING,
    )


# --- is_auto_appliable ---


def test_low_risk_kinds_are_appliable() -> None:
    assert is_auto_appliable(RecommendationKind.ADD_NEGATIVE_KEYWORD, RecommendationSeverity.MEDIUM)
    assert is_auto_appliable(RecommendationKind.PAUSE_KEYWORD, RecommendationSeverity.LOW)
    assert is_auto_appliable(
        RecommendationKind.NEGATIVE_KEYWORD_CONFLICT, RecommendationSeverity.HIGH
    )


def test_non_executable_search_term_waste_not_appliable() -> None:
    # SEARCH_TERM_WASTE is advisory (non-executable) — never auto-applied.
    assert (
        is_auto_appliable(RecommendationKind.SEARCH_TERM_WASTE, RecommendationSeverity.MEDIUM)
        is False
    )


def test_spend_increasing_kinds_never_appliable() -> None:
    for kind in (
        RecommendationKind.INCREASE_BUDGET,
        RecommendationKind.ADJUST_BUDGET,
        RecommendationKind.REALLOCATE_BUDGET,
        RecommendationKind.ADJUST_BIDDING_STRATEGY,
        RecommendationKind.RELAX_TARGET_CPA,
    ):
        assert is_auto_appliable(kind, RecommendationSeverity.LOW) is False


def test_critical_severity_not_appliable() -> None:
    assert (
        is_auto_appliable(
            RecommendationKind.ADD_NEGATIVE_KEYWORD, RecommendationSeverity.CRITICAL
        )
        is False
    )


def test_non_executable_kind_not_appliable() -> None:
    assert (
        is_auto_appliable(RecommendationKind.CPA_SPIKE, RecommendationSeverity.MEDIUM) is False
    )


# --- select_for_auto_apply ---


def test_select_disabled_returns_empty() -> None:
    recs = [_rec(RecommendationKind.ADD_NEGATIVE_KEYWORD)]
    assert select_for_auto_apply(recs, AutoApplySettings(enabled=False)) == []


def test_select_respects_daily_cap() -> None:
    recs = [_rec(RecommendationKind.ADD_NEGATIVE_KEYWORD, rid=str(i)) for i in range(10)]
    out = select_for_auto_apply(recs, AutoApplySettings(enabled=True, max_changes_per_day=3))
    assert len(out) == 3


def test_select_accounts_for_already_applied() -> None:
    recs = [_rec(RecommendationKind.ADD_NEGATIVE_KEYWORD, rid=str(i)) for i in range(10)]
    out = select_for_auto_apply(
        recs, AutoApplySettings(enabled=True, max_changes_per_day=3), already_applied_today=2
    )
    assert len(out) == 1


def test_select_filters_ineligible() -> None:
    recs = [
        _rec(RecommendationKind.INCREASE_BUDGET, rid="a"),
        _rec(RecommendationKind.ADD_NEGATIVE_KEYWORD, rid="b"),
        _rec(RecommendationKind.PAUSE_CAMPAIGN, rid="c"),
        _rec(RecommendationKind.PAUSE_KEYWORD, rid="d"),
    ]
    out = select_for_auto_apply(recs, AutoApplySettings(enabled=True, max_changes_per_day=10))
    assert [r.id for r in out] == ["b", "d"]


def test_parse_risk() -> None:
    assert parse_risk("LOW") is AutoApplyRisk.LOW
    assert parse_risk("medium") is AutoApplyRisk.MEDIUM
    assert parse_risk("nonsense") is AutoApplyRisk.LOW
    assert parse_risk(None) is AutoApplyRisk.LOW


# --- AutoApplyUseCase ---


@pytest.mark.asyncio
async def test_use_case_approves_and_audits() -> None:
    settings_repo = AsyncMock()
    settings_repo.get.return_value = AutoApplySettings(enabled=True, max_changes_per_day=5)
    rec_repo = AsyncMock()
    rec_repo.list_pending.return_value = [
        _rec(RecommendationKind.ADD_NEGATIVE_KEYWORD, rid="b"),
        _rec(RecommendationKind.INCREASE_BUDGET, rid="a"),  # ineligible
    ]
    audit_repo = AsyncMock()

    uc = AutoApplyUseCase(rec_repo, settings_repo, audit_repo)
    approved = await uc.select_and_approve(AccountId("acc-1"))

    assert [str(i) for i in approved] == ["b"]
    rec_repo.update_status.assert_awaited_once()
    # Audit entry written with actor=auto.
    audit_log = audit_repo.save.call_args.args[0]
    assert audit_log.payload["actor"] == "auto"
    assert audit_log.action == "AUTO_APPROVE"


@pytest.mark.asyncio
async def test_use_case_noop_when_disabled() -> None:
    settings_repo = AsyncMock()
    settings_repo.get.return_value = AutoApplySettings(enabled=False)
    rec_repo = AsyncMock()
    audit_repo = AsyncMock()

    uc = AutoApplyUseCase(rec_repo, settings_repo, audit_repo)
    approved = await uc.select_and_approve(AccountId("acc-1"))

    assert approved == []
    rec_repo.update_status.assert_not_awaited()
