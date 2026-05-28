"""Unit tests for GoogleAdsConversionAdapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pytest

from adcopilot.infrastructure.adapters.google_ads_conversion_adapter import (
    GoogleAdsConversionAdapter,
)


@dataclass
class _FakeConversionAction:
    name: str
    category: str
    status: str
    include_in_conversions_metric: bool
    # unused but matches ConversionActionSnapshot interface
    id: int = 0
    conversion_action_id: int = 0
    counting_type: str = "ONE_PER_CLICK"
    snapshot_date: date = field(default_factory=date.today)


class _FakeGoogleAdsClient:
    def __init__(self, actions, raises=None):
        self._actions = actions
        self._raises = raises

    async def list_conversion_actions(self, refresh_token, customer_id):
        if self._raises:
            raise self._raises
        return self._actions


@pytest.mark.asyncio
async def test_has_conversion_tracking_with_active_purchase_action():
    action = _FakeConversionAction(
        name="Purchase",
        category="PURCHASE",
        status="ENABLED",
        include_in_conversions_metric=True,
    )
    adapter = GoogleAdsConversionAdapter(_FakeGoogleAdsClient([action]))
    result = await adapter.check("token", "123")
    assert result.has_conversion_tracking is True
    assert result.conversion_action_count == 1
    assert result.active_action_names == ["Purchase"]
    assert result.is_configured is True


@pytest.mark.asyncio
async def test_no_tracking_when_all_actions_disabled():
    action = _FakeConversionAction(
        name="OldAction",
        category="LEAD",
        status="REMOVED",
        include_in_conversions_metric=True,
    )
    adapter = GoogleAdsConversionAdapter(_FakeGoogleAdsClient([action]))
    result = await adapter.check("token", "123")
    assert result.has_conversion_tracking is False
    assert result.is_configured is False


@pytest.mark.asyncio
async def test_no_tracking_when_category_not_macro():
    action = _FakeConversionAction(
        name="PageView",
        category="PAGE_VIEW",
        status="ENABLED",
        include_in_conversions_metric=True,
    )
    adapter = GoogleAdsConversionAdapter(_FakeGoogleAdsClient([action]))
    result = await adapter.check("token", "123")
    assert result.has_conversion_tracking is False


@pytest.mark.asyncio
async def test_no_tracking_when_not_included_in_conversions():
    action = _FakeConversionAction(
        name="Lead",
        category="LEAD",
        status="ENABLED",
        include_in_conversions_metric=False,
    )
    adapter = GoogleAdsConversionAdapter(_FakeGoogleAdsClient([action]))
    result = await adapter.check("token", "123")
    assert result.has_conversion_tracking is False


@pytest.mark.asyncio
async def test_api_failure_returns_safe_default():
    adapter = GoogleAdsConversionAdapter(
        _FakeGoogleAdsClient([], raises=RuntimeError("quota exceeded"))
    )
    result = await adapter.check("token", "456")
    assert result.has_conversion_tracking is False
    assert result.customer_id == "456"


@pytest.mark.asyncio
async def test_multiple_active_actions():
    actions = [
        _FakeConversionAction(
            name="Purchase",
            category="PURCHASE",
            status="ENABLED",
            include_in_conversions_metric=True,
        ),
        _FakeConversionAction(
            name="Lead Form",
            category="LEAD",
            status="ENABLED",
            include_in_conversions_metric=True,
        ),
        _FakeConversionAction(
            name="Old",
            category="SIGNUP",
            status="REMOVED",
            include_in_conversions_metric=True,
        ),
    ]
    adapter = GoogleAdsConversionAdapter(_FakeGoogleAdsClient(actions))
    result = await adapter.check("token", "789")
    assert result.conversion_action_count == 2
    assert set(result.active_action_names) == {"Purchase", "Lead Form"}
