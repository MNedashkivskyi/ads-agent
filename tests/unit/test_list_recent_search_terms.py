"""Unit tests for list_recent_search_terms GAQL query (Task 2.1)."""

from unittest.mock import MagicMock, patch

import pytest

from adcopilot.config import Settings
from adcopilot.domain.exceptions import GoogleAdsAuthError
from adcopilot.infrastructure.google_ads.queries import list_recent_search_terms


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


def _make_row(term: str, campaign_name: str, cost: int, clicks: int, impressions: int, conversions: float) -> MagicMock:
    row = MagicMock()
    row.search_term_view.search_term = term
    row.campaign.name = campaign_name
    row.metrics.cost_micros = cost
    row.metrics.clicks = clicks
    row.metrics.impressions = impressions
    row.metrics.conversions = conversions
    return row


def _batch(rows: list[MagicMock]) -> list[MagicMock]:
    b = MagicMock()
    b.results = rows
    return [b]


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_returns_top_terms_with_campaign_name(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mc = MagicMock()
    mock_build.return_value = mc
    rows = [
        _make_row("buty sportowe", "Kampania A", 500_000, 10, 200, 1.0),
        _make_row("tanie buty", "Kampania B", 300_000, 5, 100, 0.0),
    ]
    mc.get_service.return_value.search_stream.return_value = _batch(rows)

    results = await list_recent_search_terms("tok", "123-456", settings)

    assert len(results) == 2
    assert results[0].search_term == "buty sportowe"
    assert results[0].campaign_name == "Kampania A"
    assert results[0].cost_micros == 500_000
    assert results[1].search_term == "tanie buty"


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_empty_account_returns_empty_list(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mc = MagicMock()
    mock_build.return_value = mc
    mc.get_service.return_value.search_stream.return_value = _batch([])

    results = await list_recent_search_terms("tok", "123-456", settings)

    assert results == []


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_limit_passed_to_query(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mc = MagicMock()
    mock_build.return_value = mc
    mc.get_service.return_value.search_stream.return_value = _batch([])

    await list_recent_search_terms("tok", "123-456", settings, days=14, limit=5)

    call_args = mc.get_service.return_value.search_stream.call_args
    query_str = call_args.kwargs.get("query") or call_args.args[0] if call_args.args else ""
    assert "LIMIT 5" in query_str


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_reraises_auth_error(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mc = MagicMock()
    mock_build.return_value = mc
    mc.get_service.return_value.search_stream.side_effect = GoogleAdsAuthError("bad")

    with pytest.raises(GoogleAdsAuthError):
        await list_recent_search_terms("tok", "123-456", settings)
