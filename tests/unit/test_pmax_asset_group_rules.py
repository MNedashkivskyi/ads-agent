"""SH1: PMax/Shopping asset-group + feed-segmentation advisory rules + channel guard."""

from __future__ import annotations

import uuid
from datetime import date

from adcopilot.application.detection.base import DetectionContext
from adcopilot.application.detection.rules.rule_60_pmax_asset_group_health import (
    PMaxAssetGroupLimitedRule,
    PMaxAssetGroupWeakRule,
    PMaxFeedSegmentationRule,
)
from adcopilot.application.detection.rules.rule_07_budget_capped import BudgetCappedRule
from adcopilot.domain.entities import AccountId, GoogleAdsAccount, UserId
from adcopilot.domain.snapshot import AssetGroupSnapshot, CampaignSnapshot, ListingGroupSnapshot, SnapshotId

_ACC = AccountId("acc-1")
_DAY = date(2026, 6, 3)


def _account() -> GoogleAdsAccount:
    from datetime import UTC, datetime

    return GoogleAdsAccount(
        id=_ACC, user_id=UserId("u1"), customer_id="123", descriptive_name="x",
        currency="PLN", timezone="UTC", is_manager=False, write_enabled=True,
        connected_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _ag(ad_strength="GOOD", primary_status="ELIGIBLE", status="ENABLED", cid=99) -> AssetGroupSnapshot:
    return AssetGroupSnapshot(
        id=SnapshotId(str(uuid.uuid4())), account_id=_ACC, snapshot_date=_DAY,
        asset_group_id=11, campaign_id=cid, name="AG", status=status,
        ad_strength=ad_strength, primary_status=primary_status,
        impressions=100, clicks=5, cost_micros=1_000_000, conversions=1.0, conv_value=50.0,
    )


def _campaign(channel="PERFORMANCE_MAX", cost=20_000_000, cid=99) -> CampaignSnapshot:
    return CampaignSnapshot(
        id=SnapshotId(str(uuid.uuid4())), account_id=_ACC, snapshot_date=_DAY, campaign_id=cid,
        name="PMax 1", status="ENABLED", channel_type=channel, budget_micros=10_000_000,
        bidding_strategy="MAXIMIZE_CONVERSION_VALUE", impressions=1000, clicks=50,
        cost_micros=cost, conversions=10.0, conv_value=100.0,
    )


def _lg(is_catch_all=True, cid=99, lg_id=1) -> ListingGroupSnapshot:
    return ListingGroupSnapshot(
        id=SnapshotId(str(uuid.uuid4())), account_id=_ACC, snapshot_date=_DAY,
        asset_group_id=11, campaign_id=cid, listing_group_id=lg_id,
        dimension_type="" if is_catch_all else "PRODUCT_BRAND",
        case_value="" if is_catch_all else "Nike", is_catch_all=is_catch_all,
    )


def _ctx(**kw) -> DetectionContext:
    from adcopilot.application.detection.base import HistoricalStats

    return DetectionContext(
        account=_account(),
        campaigns=kw.get("campaigns", []),
        ad_groups=[], keywords=[], search_terms=[], ads=[],
        history=HistoricalStats(avg_cpa_micros=0, total_cost_micros=0, total_conversions=0.0),
        snapshot_date=_DAY,
        asset_groups=kw.get("asset_groups", []),
        listing_groups=kw.get("listing_groups", []),
    )


def test_weak_asset_group_fires() -> None:
    recs = PMaxAssetGroupWeakRule().detect(_ctx(asset_groups=[_ag(ad_strength="POOR")]))
    assert len(recs) == 1
    assert recs[0].payload["ad_strength"] == "POOR"


def test_good_asset_group_silent() -> None:
    assert PMaxAssetGroupWeakRule().detect(_ctx(asset_groups=[_ag(ad_strength="EXCELLENT")])) == []


def test_limited_asset_group_fires() -> None:
    recs = PMaxAssetGroupLimitedRule().detect(_ctx(asset_groups=[_ag(primary_status="LIMITED")]))
    assert len(recs) == 1
    assert recs[0].payload["primary_status"] == "LIMITED"


def test_feed_segmentation_fires_on_catch_all_only() -> None:
    recs = PMaxFeedSegmentationRule().detect(
        _ctx(campaigns=[_campaign()], listing_groups=[_lg(is_catch_all=True)])
    )
    assert len(recs) == 1
    assert recs[0].target["campaign_id"] == 99


def test_feed_segmentation_silent_when_segmented() -> None:
    recs = PMaxFeedSegmentationRule().detect(
        _ctx(campaigns=[_campaign()], listing_groups=[_lg(is_catch_all=False, lg_id=2)])
    )
    assert recs == []


def test_feed_segmentation_silent_when_low_spend() -> None:
    recs = PMaxFeedSegmentationRule().detect(
        _ctx(campaigns=[_campaign(cost=1_000_000)], listing_groups=[_lg(is_catch_all=True)])
    )
    assert recs == []


def test_budget_rule_skips_pmax_campaign() -> None:
    # rule_07 must not fire on a PMax campaign (channel guard).
    pmax = _campaign(channel="PERFORMANCE_MAX", cost=10_000_000)
    recs = BudgetCappedRule().detect(_ctx(campaigns=[pmax]))
    assert recs == []
