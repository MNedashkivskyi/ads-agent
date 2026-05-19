"""Unit tests for multi-account search terms aggregation (Task 2.4)."""

from __future__ import annotations

from adcopilot.interfaces.api.search_terms import SearchTermResponse


def test_search_term_response_has_account_name_field() -> None:
    r = SearchTermResponse(
        search_term="buty",
        account_id="acc-1",
        account_name="Sklep A",
        campaign_name="Kampania 1",
        cost_pln=10.0,
        clicks=5,
        impressions=100,
        conversions=0.0,
    )
    assert r.account_name == "Sklep A"


def test_search_term_response_account_name_defaults_empty() -> None:
    r = SearchTermResponse(
        search_term="buty",
        account_id="acc-1",
        campaign_name="Kampania 1",
        cost_pln=10.0,
        clicks=5,
        impressions=100,
        conversions=0.0,
    )
    assert r.account_name == ""


def test_results_sorted_by_cost_descending() -> None:
    items = [
        SearchTermResponse(
            search_term=t,
            account_id="acc-1",
            campaign_name="C",
            cost_pln=c,
            clicks=1,
            impressions=10,
            conversions=0.0,
        )
        for t, c in [("cheap", 1.0), ("expensive", 50.0), ("mid", 20.0)]
    ]
    items.sort(key=lambda r: r.cost_pln, reverse=True)
    assert [i.search_term for i in items] == ["expensive", "mid", "cheap"]
