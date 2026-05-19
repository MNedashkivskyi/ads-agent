"""Unit tests for ConversionTrackingAuditUseCase (Task 1.3)."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.application.use_cases.audit_conversion_tracking import ConversionTrackingAuditUseCase
from adcopilot.domain.conversion_audit import ConversionActionHealth
from adcopilot.domain.entities import AccountId
from adcopilot.domain.snapshot import ConversionActionSnapshot, SnapshotId


def _make_snapshot(
    name: str,
    status: str,
    all_conversions: float,
    action_id: int = 1,
) -> ConversionActionSnapshot:
    return ConversionActionSnapshot(
        id=SnapshotId("test-id"),
        account_id=AccountId("123-456"),
        snapshot_date=date(2026, 5, 19),
        conversion_action_id=action_id,
        name=name,
        category="PURCHASE",
        counting_type="ONE_PER_CLICK",
        status=status,
        include_in_conversions_metric=True,
        all_conversions=all_conversions,
    )


def _make_use_case(snapshots: list[ConversionActionSnapshot], llm_response: str = "OK po polsku") -> ConversionTrackingAuditUseCase:
    google_ads = MagicMock()
    google_ads.list_conversion_actions = AsyncMock(return_value=snapshots)

    llm = MagicMock()
    llm.complete = AsyncMock(return_value=llm_response)

    prompt_repo = MagicMock()
    prompt_repo.get_latest = AsyncMock(return_value=None)  # triggers fallback

    return ConversionTrackingAuditUseCase(google_ads=google_ads, llm=llm, prompt_repo=prompt_repo)


@pytest.mark.asyncio
async def test_healthy_action_classified_correctly() -> None:
    uc = _make_use_case([_make_snapshot("Purchase", "ENABLED", all_conversions=5.0)])

    result = await uc.execute("tok", "123-456")

    assert result.overall_health == ConversionActionHealth.HEALTHY
    assert result.action_statuses[0].health == ConversionActionHealth.HEALTHY


@pytest.mark.asyncio
async def test_stale_action_classified_correctly() -> None:
    uc = _make_use_case([_make_snapshot("Purchase", "ENABLED", all_conversions=0.0)])

    result = await uc.execute("tok", "123-456")

    assert result.overall_health == ConversionActionHealth.STALE
    assert result.action_statuses[0].health == ConversionActionHealth.STALE


@pytest.mark.asyncio
async def test_disabled_action_classified_correctly() -> None:
    uc = _make_use_case([_make_snapshot("Old", "REMOVED", all_conversions=0.0)])

    result = await uc.execute("tok", "123-456")

    assert result.action_statuses[0].health == ConversionActionHealth.DISABLED


@pytest.mark.asyncio
async def test_missing_returns_missing_health_and_gtm_guide() -> None:
    uc = _make_use_case([])

    result = await uc.execute("tok", "123-456")

    assert result.overall_health == ConversionActionHealth.MISSING
    assert result.action_statuses == []
    assert "Tag Manager" in result.diagnostic_message_pl or "GTM" in result.diagnostic_message_pl or "śledzenia" in result.diagnostic_message_pl


@pytest.mark.asyncio
async def test_mixed_statuses_overall_health_is_healthy_when_any_healthy() -> None:
    snapshots = [
        _make_snapshot("Good", "ENABLED", all_conversions=3.0, action_id=1),
        _make_snapshot("Stale", "ENABLED", all_conversions=0.0, action_id=2),
        _make_snapshot("Removed", "REMOVED", all_conversions=0.0, action_id=3),
    ]
    uc = _make_use_case(snapshots)

    result = await uc.execute("tok", "123-456")

    assert result.overall_health == ConversionActionHealth.HEALTHY
    assert len(result.action_statuses) == 3


@pytest.mark.asyncio
async def test_diagnostic_message_from_llm_returned() -> None:
    polish_msg = "Twoje śledzenie konwersji wymaga naprawy."
    uc = _make_use_case(
        [_make_snapshot("Purchase", "ENABLED", all_conversions=2.0)],
        llm_response=polish_msg,
    )

    result = await uc.execute("tok", "123-456")

    assert result.diagnostic_message_pl == polish_msg


@pytest.mark.asyncio
async def test_account_id_in_result() -> None:
    uc = _make_use_case([_make_snapshot("P", "ENABLED", all_conversions=1.0)])

    result = await uc.execute("tok", "999-000")

    assert result.account_id == AccountId("999-000")
