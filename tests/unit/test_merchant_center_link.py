"""Tests for Merchant Center connection check — Phase 6 Task 6.1."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adcopilot.application.ports.google_ads import MerchantCenterLink
from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter


def _make_adapter() -> GoogleAdsQueriesAdapter:
    settings = MagicMock()
    settings.GOOGLE_ADS_DEVELOPER_TOKEN = "dev-token"
    settings.GOOGLE_ADS_CLIENT_ID = "client-id"
    settings.GOOGLE_ADS_CLIENT_SECRET = "client-secret"
    return GoogleAdsQueriesAdapter(settings)


@pytest.mark.asyncio
async def test_get_merchant_center_link_returns_enabled_link():
    adapter = _make_adapter()
    mock_links = [
        {"feed_id": 123456, "name": "Sklep Testowy", "status": "ENABLED"},
    ]

    import adcopilot.infrastructure.google_ads.queries as q_mod

    with patch.object(q_mod, "query_merchant_center_feed", new=AsyncMock(return_value=mock_links)):
        result = await adapter.get_merchant_center_link("refresh-token", "1234567890")

    assert result is not None
    assert isinstance(result, MerchantCenterLink)
    assert result.merchant_id == 123456
    assert result.account_name == "Sklep Testowy"
    assert result.status == "ENABLED"


@pytest.mark.asyncio
async def test_get_merchant_center_link_returns_pending_link():
    adapter = _make_adapter()
    mock_links = [
        {"feed_id": 999, "name": "Sklep Pending", "status": "PENDING"},
    ]

    import adcopilot.infrastructure.google_ads.queries as q_mod

    with patch.object(q_mod, "query_merchant_center_feed", new=AsyncMock(return_value=mock_links)):
        result = await adapter.get_merchant_center_link("refresh-token", "111")

    assert result is not None
    assert result.merchant_id == 999
    assert result.status == "PENDING"


@pytest.mark.asyncio
async def test_get_merchant_center_link_returns_none_when_no_links():
    adapter = _make_adapter()

    import adcopilot.infrastructure.google_ads.queries as q_mod

    with patch.object(q_mod, "query_merchant_center_feed", new=AsyncMock(return_value=[])):
        result = await adapter.get_merchant_center_link("refresh-token", "222")

    assert result is None


@pytest.mark.asyncio
async def test_get_merchant_center_link_returns_none_for_non_enabled_status():
    adapter = _make_adapter()
    mock_links = [
        {"feed_id": 777, "name": "Sklep", "status": "INACTIVE"},
        {"feed_id": 888, "name": "Sklep2", "status": "UNKNOWN"},
    ]

    import adcopilot.infrastructure.google_ads.queries as q_mod

    with patch.object(q_mod, "query_merchant_center_feed", new=AsyncMock(return_value=mock_links)):
        result = await adapter.get_merchant_center_link("refresh-token", "333")

    assert result is None


@pytest.mark.asyncio
async def test_get_merchant_center_link_returns_first_enabled():
    adapter = _make_adapter()
    mock_links = [
        {"feed_id": 1, "name": "Sklep A", "status": "ENABLED"},
        {"feed_id": 2, "name": "Sklep B", "status": "ENABLED"},
    ]

    import adcopilot.infrastructure.google_ads.queries as q_mod

    with patch.object(q_mod, "query_merchant_center_feed", new=AsyncMock(return_value=mock_links)):
        result = await adapter.get_merchant_center_link("refresh-token", "444")

    assert result is not None
    assert result.merchant_id == 1


def test_merchant_center_link_dataclass():
    link = MerchantCenterLink(merchant_id=42, account_name="Test", status="ENABLED")
    assert link.merchant_id == 42
    assert link.account_name == "Test"
    assert link.status == "ENABLED"
