"""SH0: row-parsing for asset-group + listing-group GAQL queries (mocked client)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from adcopilot.config import Settings
from adcopilot.infrastructure.google_ads import queries


class _Stream:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        yield SimpleNamespace(results=self._rows)


class _Service:
    def __init__(self, rows):
        self._rows = rows

    def search_stream(self, customer_id, query):
        return _Stream(self._rows)


class _Client:
    def __init__(self, rows):
        self._rows = rows

    def get_service(self, name):
        return _Service(self._rows)


@pytest.mark.asyncio
async def test_query_asset_groups_maps_rows(monkeypatch) -> None:
    row = SimpleNamespace(
        asset_group=SimpleNamespace(
            id=11,
            name="AG1",
            status=SimpleNamespace(name="ENABLED"),
            ad_strength=SimpleNamespace(name="POOR"),
            primary_status=SimpleNamespace(name="LIMITED"),
        ),
        campaign=SimpleNamespace(id=99),
        metrics=SimpleNamespace(
            impressions=1000, clicks=50, cost_micros=2_000_000, conversions=3.0, conversions_value=600.0
        ),
    )
    monkeypatch.setattr(queries, "_build_client", lambda rt, s: _Client([row]))

    result = await queries.query_asset_groups("tok", "123-456-7890", date(2026, 6, 3), Settings())

    assert len(result) == 1
    ag = result[0]
    assert ag.asset_group_id == 11
    assert ag.campaign_id == 99
    assert ag.ad_strength == "POOR"
    assert ag.primary_status == "LIMITED"
    assert ag.conv_value == 600.0


@pytest.mark.asyncio
async def test_query_listing_groups_classifies_catch_all_and_brand(monkeypatch) -> None:
    catch_all = SimpleNamespace(
        asset_group_listing_group_filter=SimpleNamespace(
            id=1,
            type_=SimpleNamespace(name="UNIT_INCLUDED"),
            case_value=SimpleNamespace(
                product_category=SimpleNamespace(category_id=0),
                product_brand=SimpleNamespace(value=""),
            ),
        ),
        asset_group=SimpleNamespace(id=11),
        campaign=SimpleNamespace(id=99),
    )
    branded = SimpleNamespace(
        asset_group_listing_group_filter=SimpleNamespace(
            id=2,
            type_=SimpleNamespace(name="UNIT_INCLUDED"),
            case_value=SimpleNamespace(
                product_category=SimpleNamespace(category_id=0),
                product_brand=SimpleNamespace(value="Nike"),
            ),
        ),
        asset_group=SimpleNamespace(id=11),
        campaign=SimpleNamespace(id=99),
    )
    monkeypatch.setattr(queries, "_build_client", lambda rt, s: _Client([catch_all, branded]))

    result = await queries.query_listing_group_filters("tok", "123-456-7890", Settings())

    assert len(result) == 2
    assert result[0].is_catch_all is True
    assert result[0].dimension_type == ""
    assert result[1].is_catch_all is False
    assert result[1].dimension_type == "PRODUCT_BRAND"
    assert result[1].case_value == "Nike"
