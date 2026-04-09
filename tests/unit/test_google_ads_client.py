"""
Unit tests for the Google Ads client adapter using mocked google-ads library responses.
"""

from unittest.mock import MagicMock, patch

import pytest

from adcopilot.application.ports.google_ads import CustomerInfo
from adcopilot.config import Settings
from adcopilot.domain.exceptions import GoogleAdsAuthError, GoogleAdsUnavailable
from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter

TEST_REFRESH_TOKEN = "test-refresh-token"


def _make_settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql+asyncpg://x:x@localhost/x",
        REDIS_URL="redis://localhost:6379/0",
        SECRET_KEY="test-secret",
        TOKEN_ENCRYPTION_KEY="test-enc-key-32b",
        GOOGLE_ADS_DEVELOPER_TOKEN="dev-token",
        GOOGLE_ADS_CLIENT_ID="client-id",
        GOOGLE_ADS_CLIENT_SECRET="client-secret",
    )


@pytest.fixture
def adapter() -> GoogleAdsClientAdapter:
    return GoogleAdsClientAdapter(_make_settings())


@patch("adcopilot.infrastructure.google_ads.client.GoogleAdsClientAdapter._build_client")
async def test_list_accessible_customers_returns_resource_names(
    mock_build: MagicMock, adapter: GoogleAdsClientAdapter
) -> None:
    mock_client = MagicMock()
    mock_build.return_value = mock_client

    mock_response = MagicMock()
    mock_response.resource_names = ["customers/111", "customers/222"]
    mock_client.get_service.return_value.list_accessible_customers.return_value = mock_response

    result = await adapter.list_accessible_customers(TEST_REFRESH_TOKEN)

    assert result == ["customers/111", "customers/222"]
    mock_client.get_service.assert_called_once_with("CustomerService")


@patch("adcopilot.infrastructure.google_ads.client.GoogleAdsClientAdapter._build_client")
async def test_list_accessible_customers_auth_error(
    mock_build: MagicMock, adapter: GoogleAdsClientAdapter
) -> None:
    mock_client = MagicMock()
    mock_build.return_value = mock_client
    mock_client.get_service.return_value.list_accessible_customers.side_effect = Exception(
        "Request had invalid authentication credentials. UNAUTHENTICATED"
    )

    with pytest.raises(GoogleAdsAuthError):
        await adapter.list_accessible_customers(TEST_REFRESH_TOKEN)


@patch("adcopilot.infrastructure.google_ads.client.GoogleAdsClientAdapter._build_client")
async def test_list_accessible_customers_unavailable(
    mock_build: MagicMock, adapter: GoogleAdsClientAdapter
) -> None:
    mock_client = MagicMock()
    mock_build.return_value = mock_client
    mock_client.get_service.return_value.list_accessible_customers.side_effect = Exception(
        "Service temporarily unavailable"
    )

    with pytest.raises(GoogleAdsUnavailable):
        await adapter.list_accessible_customers(TEST_REFRESH_TOKEN)


@patch("adcopilot.infrastructure.google_ads.client.GoogleAdsClientAdapter._build_client")
async def test_get_customer_info_returns_customer_info(
    mock_build: MagicMock, adapter: GoogleAdsClientAdapter
) -> None:
    mock_client = MagicMock()
    mock_build.return_value = mock_client

    mock_row = MagicMock()
    mock_row.customer.descriptive_name = "Acme Corp"
    mock_row.customer.currency_code = "USD"
    mock_row.customer.time_zone = "America/New_York"
    mock_row.customer.manager = False

    mock_client.get_service.return_value.search.return_value = [mock_row]

    result = await adapter.get_customer_info(TEST_REFRESH_TOKEN, "123-456-7890")

    assert isinstance(result, CustomerInfo)
    assert result.descriptive_name == "Acme Corp"
    assert result.currency == "USD"
    assert result.timezone == "America/New_York"
    assert result.is_manager is False


@patch("adcopilot.infrastructure.google_ads.client.GoogleAdsClientAdapter._build_client")
async def test_get_customer_info_no_rows_raises_unavailable(
    mock_build: MagicMock, adapter: GoogleAdsClientAdapter
) -> None:
    mock_client = MagicMock()
    mock_build.return_value = mock_client
    mock_client.get_service.return_value.search.return_value = []

    with pytest.raises(GoogleAdsUnavailable):
        await adapter.get_customer_info(TEST_REFRESH_TOKEN, "000")


@patch("adcopilot.infrastructure.google_ads.client.GoogleAdsClientAdapter._build_client")
async def test_build_client_failure_raises_unavailable(
    mock_build: MagicMock, adapter: GoogleAdsClientAdapter
) -> None:
    mock_build.side_effect = GoogleAdsUnavailable("Failed to build Google Ads client: oops")

    with pytest.raises(GoogleAdsUnavailable):
        await adapter.list_accessible_customers(TEST_REFRESH_TOKEN)
