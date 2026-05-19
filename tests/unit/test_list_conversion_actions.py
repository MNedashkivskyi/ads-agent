"""Unit tests for list_conversion_actions GAQL query (Task 1.2)."""

from unittest.mock import MagicMock, patch

import pytest

from adcopilot.config import Settings
from adcopilot.domain.exceptions import GoogleAdsAuthError
from adcopilot.infrastructure.google_ads.queries import list_conversion_actions


def _make_settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql+asyncpg://x:x@localhost/x",
        REDIS_URL="redis://localhost:6379/0",
        SECRET_KEY="test",
        TOKEN_ENCRYPTION_KEY="test-enc-key-32b",
        GOOGLE_ADS_DEVELOPER_TOKEN="dev",
        GOOGLE_ADS_CLIENT_ID="cid",
        GOOGLE_ADS_CLIENT_SECRET="csec",
    )


def _make_stream_batch(rows: list[MagicMock]) -> list[MagicMock]:
    batch = MagicMock()
    batch.results = rows
    return [batch]


def _make_row(
    action_id: int,
    name: str,
    status: str,
    category: str = "PURCHASE",
    counting_type: str = "ONE_PER_CLICK",
    include_in_conversions: bool = True,
    all_conversions: float = 0.0,
) -> MagicMock:
    row = MagicMock()
    row.conversion_action.id = action_id
    row.conversion_action.name = name
    row.conversion_action.status.name = status
    row.conversion_action.category.name = category
    row.conversion_action.counting_type.name = counting_type
    row.conversion_action.include_in_conversions_metric = include_in_conversions
    row.metrics.all_conversions = all_conversions
    return row


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_list_conversion_actions_maps_fields(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mock_client = MagicMock()
    mock_build.return_value = mock_client

    row = _make_row(42, "Purchase", "ENABLED", all_conversions=10.0)
    mock_client.get_service.return_value.search_stream.return_value = _make_stream_batch([row])

    results = await list_conversion_actions("tok", "123-456-7890", settings)

    assert len(results) == 1
    a = results[0]
    assert a.conversion_action_id == 42
    assert a.name == "Purchase"
    assert a.status == "ENABLED"
    assert a.category == "PURCHASE"
    assert a.all_conversions == 10.0


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_list_conversion_actions_returns_correct_statuses(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mock_client = MagicMock()
    mock_build.return_value = mock_client

    rows = [
        _make_row(1, "Purchase", "ENABLED", all_conversions=5.0),
        _make_row(2, "Signup", "ENABLED", all_conversions=0.0),
        _make_row(3, "Old action", "HIDDEN", all_conversions=0.0),
    ]
    mock_client.get_service.return_value.search_stream.return_value = _make_stream_batch(rows)

    results = await list_conversion_actions("tok", "123-456-7890", settings)

    assert len(results) == 3
    statuses = {r.name: r.status for r in results}
    assert statuses["Purchase"] == "ENABLED"
    assert statuses["Signup"] == "ENABLED"
    assert statuses["Old action"] == "HIDDEN"

    conversions = {r.name: r.all_conversions for r in results}
    assert conversions["Purchase"] == 5.0
    assert conversions["Signup"] == 0.0


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_list_conversion_actions_empty_account(mock_build: MagicMock) -> None:
    """Accounts with no conversion actions return an empty list."""
    settings = _make_settings()
    mock_client = MagicMock()
    mock_build.return_value = mock_client
    mock_client.get_service.return_value.search_stream.return_value = _make_stream_batch([])

    results = await list_conversion_actions("tok", "123-456-7890", settings)

    assert results == []


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_list_conversion_actions_reraises_auth_error(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mock_client = MagicMock()
    mock_build.return_value = mock_client
    mock_client.get_service.return_value.search_stream.side_effect = GoogleAdsAuthError("bad token")

    with pytest.raises(GoogleAdsAuthError):
        await list_conversion_actions("tok", "123-456-7890", settings)
