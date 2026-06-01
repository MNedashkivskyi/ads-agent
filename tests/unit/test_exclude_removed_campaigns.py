"""Unit tests for _exclude_removed_campaigns (detection skips deleted campaigns)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from adcopilot.application.ports.snapshot_repository import SnapshotData
from adcopilot.application.use_cases.run_detection import _exclude_removed_campaigns
from adcopilot.domain.entities import AccountId
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    CampaignSnapshot,
    KeywordSnapshot,
    NegativeKeywordSnapshot,
    SearchTermSnapshot,
    SnapshotId,
)

_ACCT = AccountId(str(uuid.uuid4()))
_DATE = datetime(2026, 5, 31, tzinfo=UTC).date()


def _sid() -> SnapshotId:
    return SnapshotId(str(uuid.uuid4()))


def _campaign(campaign_id: int, status: str) -> CampaignSnapshot:
    return CampaignSnapshot(
        id=_sid(),
        account_id=_ACCT,
        snapshot_date=_DATE,
        campaign_id=campaign_id,
        name=f"camp-{campaign_id}",
        status=status,
        channel_type="SEARCH",
        budget_micros=1_000_000,
        bidding_strategy="MAXIMIZE_CLICKS",
        impressions=10,
        clicks=1,
        cost_micros=1000,
        conversions=0.0,
        conv_value=0.0,
    )


def _ad_group(ad_group_id: int, campaign_id: int) -> AdGroupSnapshot:
    return AdGroupSnapshot(
        id=_sid(),
        account_id=_ACCT,
        snapshot_date=_DATE,
        ad_group_id=ad_group_id,
        campaign_id=campaign_id,
        name=f"ag-{ad_group_id}",
        status="ENABLED",
        impressions=10,
        clicks=1,
        cost_micros=1000,
        conversions=0.0,
    )


def _keyword(criterion_id: int, ad_group_id: int) -> KeywordSnapshot:
    return KeywordSnapshot(
        id=_sid(),
        account_id=_ACCT,
        snapshot_date=_DATE,
        criterion_id=criterion_id,
        ad_group_id=ad_group_id,
        text="kw",
        match_type="EXACT",
        status="ENABLED",
        quality_score=None,
        impressions=1,
        clicks=0,
        cost_micros=0,
        conversions=0.0,
        ctr=0.0,
        avg_cpc_micros=0,
    )


def _ad(ad_id: int, ad_group_id: int) -> AdSnapshot:
    return AdSnapshot(
        id=_sid(),
        account_id=_ACCT,
        snapshot_date=_DATE,
        ad_id=ad_id,
        ad_group_id=ad_group_id,
        type="RESPONSIVE_SEARCH_AD",
        status="ENABLED",
        headlines_json="[]",
        descriptions_json="[]",
        final_urls_json="[]",
        impressions=1,
        clicks=0,
        cost_micros=0,
        conversions=0.0,
    )


def _search_term(ad_group_id: int) -> SearchTermSnapshot:
    return SearchTermSnapshot(
        id=_sid(),
        account_id=_ACCT,
        snapshot_date=_DATE,
        search_term="term",
        ad_group_id=ad_group_id,
        impressions=1,
        clicks=0,
        cost_micros=0,
        conversions=0.0,
        matched_keyword_id=None,
    )


def _negative(campaign_id: int, ad_group_id: int = 0) -> NegativeKeywordSnapshot:
    return NegativeKeywordSnapshot(
        id=_sid(),
        account_id=_ACCT,
        snapshot_date=_DATE,
        criterion_id=uuid.uuid4().int % 100000,
        campaign_id=campaign_id,
        ad_group_id=ad_group_id,
        text="neg",
        match_type="EXACT",
    )


def test_removed_campaign_and_children_are_excluded() -> None:
    # campaign 1 ENABLED, campaign 2 REMOVED
    snapshot = SnapshotData(
        campaigns=[_campaign(1, "ENABLED"), _campaign(2, "REMOVED")],
        ad_groups=[_ad_group(10, 1), _ad_group(20, 2)],
        keywords=[_keyword(100, 10), _keyword(200, 20)],
        search_terms=[_search_term(10), _search_term(20)],
        ads=[_ad(1000, 10), _ad(2000, 20)],
        negative_keywords=[_negative(1), _negative(2), _negative(2, ad_group_id=20)],
    )

    result = _exclude_removed_campaigns(snapshot)

    assert [c.campaign_id for c in result.campaigns] == [1]
    assert [ag.ad_group_id for ag in result.ad_groups] == [10]
    assert [k.ad_group_id for k in result.keywords] == [10]
    assert [s.ad_group_id for s in result.search_terms] == [10]
    assert [a.ad_group_id for a in result.ads] == [10]
    assert [n.campaign_id for n in result.negative_keywords] == [1]


def test_no_removed_campaigns_is_a_noop() -> None:
    snapshot = SnapshotData(
        campaigns=[_campaign(1, "ENABLED"), _campaign(2, "PAUSED")],
        ad_groups=[_ad_group(10, 1)],
        keywords=[],
        search_terms=[],
        ads=[],
        negative_keywords=[],
    )

    result = _exclude_removed_campaigns(snapshot)

    assert [c.campaign_id for c in result.campaigns] == [1, 2]
    assert [ag.ad_group_id for ag in result.ad_groups] == [10]
