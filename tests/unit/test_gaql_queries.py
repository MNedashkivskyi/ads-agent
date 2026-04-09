"""Unit tests for GAQL query functions using mocked google-ads SearchStream."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from adcopilot.config import Settings
from adcopilot.domain.exceptions import GoogleAdsAuthError, GoogleAdsUnavailable
from adcopilot.infrastructure.google_ads.queries import (
    query_ad_groups,
    query_ads,
    query_campaigns,
    query_keywords,
    query_search_terms,
)

TEST_CUSTOMER_ID = "123-456-7890"
TEST_DATE = date(2026, 1, 15)
TEST_REFRESH_TOKEN = "test-refresh-token"


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


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_query_campaigns_maps_to_dto(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mock_client = MagicMock()
    mock_build.return_value = mock_client

    row = MagicMock()
    row.campaign.id = 111
    row.campaign.name = "Summer Sale"
    row.campaign.status.name = "ENABLED"
    row.campaign.advertising_channel_type.name = "SEARCH"
    row.campaign.bidding_strategy_type.name = "TARGET_CPA"
    row.campaign_budget.amount_micros = 5_000_000
    row.metrics.impressions = 1000
    row.metrics.clicks = 50
    row.metrics.cost_micros = 2_000_000
    row.metrics.conversions = 5.0
    row.metrics.conversions_value = 500.0

    mock_client.get_service.return_value.search_stream.return_value = _make_stream_batch([row])

    results = await query_campaigns(TEST_REFRESH_TOKEN, TEST_CUSTOMER_ID, TEST_DATE, settings)

    assert len(results) == 1
    c = results[0]
    assert c.campaign_id == 111
    assert c.name == "Summer Sale"
    assert c.status == "ENABLED"
    assert c.channel_type == "SEARCH"
    assert c.budget_micros == 5_000_000
    assert c.impressions == 1000
    assert c.clicks == 50
    assert c.cost_micros == 2_000_000
    assert c.conversions == 5.0
    assert c.snapshot_date == TEST_DATE


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_query_ad_groups_maps_to_dto(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mock_client = MagicMock()
    mock_build.return_value = mock_client

    row = MagicMock()
    row.ad_group.id = 222
    row.ad_group.name = "Brand KW"
    row.ad_group.status.name = "ENABLED"
    row.campaign.id = 111
    row.metrics.impressions = 500
    row.metrics.clicks = 25
    row.metrics.cost_micros = 1_000_000
    row.metrics.conversions = 2.0

    mock_client.get_service.return_value.search_stream.return_value = _make_stream_batch([row])

    results = await query_ad_groups(TEST_REFRESH_TOKEN, TEST_CUSTOMER_ID, TEST_DATE, settings)

    assert len(results) == 1
    ag = results[0]
    assert ag.ad_group_id == 222
    assert ag.campaign_id == 111
    assert ag.name == "Brand KW"
    assert ag.impressions == 500


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_query_keywords_maps_to_dto(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mock_client = MagicMock()
    mock_build.return_value = mock_client

    row = MagicMock()
    row.ad_group_criterion.criterion_id = 333
    row.ad_group_criterion.ad_group = "customers/123/adGroups/222"
    row.ad_group_criterion.keyword.text = "running shoes"
    row.ad_group_criterion.keyword.match_type.name = "EXACT"
    row.ad_group_criterion.status.name = "ENABLED"
    row.ad_group_criterion.quality_info.quality_score = 8
    row.metrics.impressions = 300
    row.metrics.clicks = 10
    row.metrics.cost_micros = 800_000
    row.metrics.conversions = 1.0
    row.metrics.ctr = 0.033
    row.metrics.average_cpc = 80_000

    mock_client.get_service.return_value.search_stream.return_value = _make_stream_batch([row])

    results = await query_keywords(TEST_REFRESH_TOKEN, TEST_CUSTOMER_ID, TEST_DATE, settings)

    assert len(results) == 1
    kw = results[0]
    assert kw.criterion_id == 333
    assert kw.ad_group_id == 222
    assert kw.text == "running shoes"
    assert kw.match_type == "EXACT"
    assert kw.quality_score == 8
    assert kw.avg_cpc_micros == 80_000


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_query_search_terms_maps_to_dto(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mock_client = MagicMock()
    mock_build.return_value = mock_client

    row = MagicMock()
    row.search_term_view.search_term = "best running shoes"
    row.search_term_view.ad_group = "customers/123/adGroups/222"
    row.metrics.impressions = 100
    row.metrics.clicks = 8
    row.metrics.cost_micros = 400_000
    row.metrics.conversions = 0.5

    mock_client.get_service.return_value.search_stream.return_value = _make_stream_batch([row])

    results = await query_search_terms(TEST_REFRESH_TOKEN, TEST_CUSTOMER_ID, TEST_DATE, settings)

    assert len(results) == 1
    st = results[0]
    assert st.search_term == "best running shoes"
    assert st.ad_group_id == 222
    assert st.clicks == 8


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_query_ads_maps_to_dto(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mock_client = MagicMock()
    mock_build.return_value = mock_client

    row = MagicMock()
    row.ad_group_ad.ad.id = 444
    row.ad_group_ad.ad_group = "customers/123/adGroups/222"
    row.ad_group_ad.ad.type_.name = "RESPONSIVE_SEARCH_AD"
    row.ad_group_ad.status.name = "ENABLED"
    hl1, hl2 = MagicMock(), MagicMock()
    hl1.text = "Buy Now"
    hl2.text = "Free Shipping"
    row.ad_group_ad.ad.responsive_search_ad.headlines = [hl1, hl2]
    d1 = MagicMock()
    d1.text = "Shop our collection"
    row.ad_group_ad.ad.responsive_search_ad.descriptions = [d1]
    row.ad_group_ad.ad.final_urls = ["https://example.com"]
    row.metrics.impressions = 200
    row.metrics.clicks = 15
    row.metrics.cost_micros = 600_000
    row.metrics.conversions = 3.0

    mock_client.get_service.return_value.search_stream.return_value = _make_stream_batch([row])

    results = await query_ads(TEST_REFRESH_TOKEN, TEST_CUSTOMER_ID, TEST_DATE, settings)

    assert len(results) == 1
    ad = results[0]
    assert ad.ad_id == 444
    assert ad.ad_group_id == 222
    assert ad.type == "RESPONSIVE_SEARCH_AD"
    assert '"Buy Now"' in ad.headlines_json
    assert '"https://example.com"' in ad.final_urls_json


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_query_campaigns_auth_error(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mock_client = MagicMock()
    mock_build.return_value = mock_client
    mock_client.get_service.return_value.search_stream.side_effect = Exception(
        "Request had invalid authentication credentials. UNAUTHENTICATED"
    )

    with pytest.raises(GoogleAdsAuthError):
        await query_campaigns(TEST_REFRESH_TOKEN, TEST_CUSTOMER_ID, TEST_DATE, settings)


@patch("adcopilot.infrastructure.google_ads.queries._build_client")
async def test_query_campaigns_unavailable(mock_build: MagicMock) -> None:
    settings = _make_settings()
    mock_client = MagicMock()
    mock_build.return_value = mock_client
    mock_client.get_service.return_value.search_stream.side_effect = Exception(
        "Service temporarily unavailable"
    )

    with pytest.raises(GoogleAdsUnavailable):
        await query_campaigns(TEST_REFRESH_TOKEN, TEST_CUSTOMER_ID, TEST_DATE, settings)
