"""Unit tests for Rule 45 — Landing Page Keyword Mismatch."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, UTC, datetime
from unittest.mock import MagicMock

import pytest

from adcopilot.application.detection.base import DetectionContext, HistoricalStats, LandingPageData
from adcopilot.application.detection.rules.rule_45_landing_page_keyword_mismatch import (
    LandingPageKeywordMismatchRule,
)
from adcopilot.domain.recommendation import RecommendationKind


def _make_ctx(ads, keywords, lp_results=None):
    account = MagicMock()
    account.id = "acc-1"
    return DetectionContext(
        account=account,
        campaigns=[],
        ad_groups=[],
        keywords=keywords,
        search_terms=[],
        ads=ads,
        history=HistoricalStats(avg_cpa_micros=0, total_cost_micros=0, total_conversions=0),
        snapshot_date=date(2024, 1, 1),
        landing_page_results=lp_results or {},
    )


def _make_ad(ad_id: int, ad_group_id: int, url: str):
    ad = MagicMock()
    ad.ad_id = ad_id
    ad.ad_group_id = ad_group_id
    ad.status = "ENABLED"
    ad.final_urls_json = json.dumps([url])
    return ad


def _make_kw(ad_group_id: int, text: str, impressions: int = 500):
    kw = MagicMock()
    kw.ad_group_id = ad_group_id
    kw.text = text
    kw.impressions = impressions
    return kw


def _make_lp(url: str, body: str, reachable: bool = True) -> LandingPageData:
    return LandingPageData(
        url=url,
        reachable=reachable,
        page_title="Test",
        h1_text="",
        body_text_sample=body,
    )


_URL = "https://example.com/"
_rule = LandingPageKeywordMismatchRule()


def test_no_landing_page_data_returns_empty():
    ctx = _make_ctx(
        ads=[_make_ad(1, 10, _URL)],
        keywords=[_make_kw(10, "kancelaria prawna")],
        lp_results={},
    )
    assert _rule.detect(ctx) == []


def test_mismatching_keywords_fires_recommendation():
    ctx = _make_ctx(
        ads=[_make_ad(1, 10, _URL)],
        keywords=[_make_kw(10, "kancelaria prawna"), _make_kw(10, "prawnik Warszawa")],
        lp_results={_URL: _make_lp(_URL, "sklep internetowy buty obuwie sandały")},
    )
    recs = _rule.detect(ctx)
    assert len(recs) == 1
    assert recs[0].kind == RecommendationKind.LANDING_PAGE_KEYWORD_MISMATCH
    assert recs[0].evidence["overlap_ratio"] < 0.30


def test_matching_keywords_no_recommendation():
    ctx = _make_ctx(
        ads=[_make_ad(1, 10, _URL)],
        keywords=[_make_kw(10, "kancelaria prawna"), _make_kw(10, "prawnik usługi")],
        lp_results={_URL: _make_lp(_URL, "kancelaria prawna obsługa Warszawa prawnik usługi firm")},
    )
    recs = _rule.detect(ctx)
    assert recs == []


def test_unreachable_page_skipped():
    ctx = _make_ctx(
        ads=[_make_ad(1, 10, _URL)],
        keywords=[_make_kw(10, "kancelaria prawna")],
        lp_results={_URL: _make_lp(_URL, "", reachable=False)},
    )
    assert _rule.detect(ctx) == []


def test_low_impression_keywords_ignored():
    ctx = _make_ctx(
        ads=[_make_ad(1, 10, _URL)],
        keywords=[_make_kw(10, "kancelaria prawna", impressions=10)],
        lp_results={_URL: _make_lp(_URL, "sklep buty obuwie")},
    )
    assert _rule.detect(ctx) == []


def test_paused_ad_skipped():
    ad = _make_ad(1, 10, _URL)
    ad.status = "PAUSED"
    ctx = _make_ctx(
        ads=[ad],
        keywords=[_make_kw(10, "kancelaria prawna")],
        lp_results={_URL: _make_lp(_URL, "sklep buty")},
    )
    assert _rule.detect(ctx) == []
