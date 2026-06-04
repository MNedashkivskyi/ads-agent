"""Unit tests for SetupConversionTrackingUseCase and VerifyConversionFiringUseCase."""

from __future__ import annotations

from datetime import date

import pytest

from adcopilot.application.use_cases.launch.setup_conversion_tracking import (
    SetupConversionTrackingUseCase,
)
from adcopilot.application.use_cases.launch.verify_conversion_firing import (
    VerifyConversionFiringUseCase,
)
from adcopilot.domain.conversion_tracking.setup import InvalidConversionCategory
from adcopilot.domain.entities import AccountId
from adcopilot.domain.snapshot import ConversionActionSnapshot, SnapshotId
from adcopilot.infrastructure.google_ads.fake_mutations import FakeGoogleAdsMutations


def _ca(
    *,
    conversion_action_id: int = 1,
    category: str = "PURCHASE",
    status: str = "ENABLED",
    include: bool = True,
    all_conversions: float = 0.0,
) -> ConversionActionSnapshot:
    return ConversionActionSnapshot(
        id=SnapshotId("00000000-0000-0000-0000-000000000001"),
        account_id=AccountId("123"),
        snapshot_date=date.today(),
        conversion_action_id=conversion_action_id,
        name="test",
        category=category,
        counting_type="ONE_PER_CLICK",
        status=status,
        include_in_conversions_metric=include,
        all_conversions=all_conversions,
    )


class FakeReader:
    def __init__(self, actions: list[ConversionActionSnapshot]) -> None:
        self._actions = actions
        self.calls: list[tuple[str, str]] = []

    async def list_conversion_actions(self, refresh_token, customer_id):
        self.calls.append((refresh_token, customer_id))
        return self._actions


# --------------------------------------------------------------------------- #
# SetupConversionTrackingUseCase
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_setup_creates_action_when_none_exists():
    reader = FakeReader([])  # no macro tracking
    writer = FakeGoogleAdsMutations()
    uc = SetupConversionTrackingUseCase(reader, writer)

    result = await uc.execute(
        refresh_token="rt",
        customer_id="123-456-7890",
        category="LEAD",
        platform="wordpress",
        value_micros=50_000_000,
    )

    assert result.already_configured is False
    assert result.conversion_action_id == 555555
    assert result.tag is not None
    assert result.tag.send_to == "AW-123456789/AbC-D_efGhIjk"
    assert result.guide is not None
    assert result.guide.platform == "wordpress"

    created = [c for c in writer.calls if c["method"] == "create_conversion_action"]
    assert len(created) == 1
    assert created[0]["category"] == "LEAD"
    assert created[0]["value_micros"] == 50_000_000
    assert created[0]["name"] == "Kontakt / Zapytanie"  # Polish default


@pytest.mark.asyncio
async def test_setup_noops_when_macro_tracking_exists():
    reader = FakeReader([_ca(category="PURCHASE")])
    writer = FakeGoogleAdsMutations()
    uc = SetupConversionTrackingUseCase(reader, writer)

    result = await uc.execute(
        refresh_token="rt",
        customer_id="123",
        category="PURCHASE",
    )

    assert result.already_configured is True
    assert result.conversion_action_id is None
    assert result.tag is None
    # No write should have happened.
    assert not any(c["method"] == "create_conversion_action" for c in writer.calls)


@pytest.mark.asyncio
async def test_setup_rejects_non_macro_category():
    uc = SetupConversionTrackingUseCase(FakeReader([]), FakeGoogleAdsMutations())
    with pytest.raises(InvalidConversionCategory):
        await uc.execute(refresh_token="rt", customer_id="123", category="PAGE_VIEW")


# --------------------------------------------------------------------------- #
# VerifyConversionFiringUseCase
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_verify_reports_firing_when_conversions_recorded():
    reader = FakeReader([_ca(conversion_action_id=7, all_conversions=3.0)])
    uc = VerifyConversionFiringUseCase(reader)

    status = await uc.execute(refresh_token="rt", customer_id="123", conversion_action_id=7)

    assert status.found is True
    assert status.enabled is True
    assert status.is_firing is True
    assert status.recent_conversions == 3.0


@pytest.mark.asyncio
async def test_verify_enabled_but_no_conversions_yet():
    reader = FakeReader([_ca(conversion_action_id=7, all_conversions=0.0)])
    uc = VerifyConversionFiringUseCase(reader)

    status = await uc.execute(refresh_token="rt", customer_id="123", conversion_action_id=7)

    assert status.found is True
    assert status.enabled is True
    assert status.is_firing is False


@pytest.mark.asyncio
async def test_verify_action_not_found():
    reader = FakeReader([_ca(conversion_action_id=1)])
    uc = VerifyConversionFiringUseCase(reader)

    status = await uc.execute(refresh_token="rt", customer_id="123", conversion_action_id=999)

    assert status.found is False
    assert status.is_firing is False


@pytest.mark.asyncio
async def test_verify_disabled_action_not_firing():
    reader = FakeReader([_ca(conversion_action_id=7, status="HIDDEN", all_conversions=5.0)])
    uc = VerifyConversionFiringUseCase(reader)

    status = await uc.execute(refresh_token="rt", customer_id="123", conversion_action_id=7)

    assert status.found is True
    assert status.enabled is False
    assert status.is_firing is False
