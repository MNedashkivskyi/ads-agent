"""Phase C: manual-era rules are suppressed on Smart Bidding campaigns but
still fire on manual campaigns. Reuses the fixtures from test_detection_rules.
"""

from __future__ import annotations

from tests.unit.test_detection_rules import (
    _campaign,
    _ad_group,
    _ctx,
    _device_perf,
    _dow_perf,
    _history,
    _hour_perf,
    _keyword,
    _search_term,
)

from adcopilot.application.detection.rules.rule_05_broad_match_bleeding import (
    BroadMatchBleedingRule,
)
from adcopilot.application.detection.rules.rule_27_match_type_redundancy import (
    MatchTypeRedundancyRule,
)
from adcopilot.application.detection.rules.rule_28_device_bid_adjustment import (
    DeviceBidAdjustmentRule,
)
from adcopilot.application.detection.rules.rule_30_ad_schedule_adjustment import (
    AdScheduleAdjustmentRule,
)
from adcopilot.application.detection.rules.rule_31_day_of_week_bid_adjustment import (
    DayOfWeekBidAdjustmentRule,
)

SMART = "TARGET_CPA"
MANUAL = "MANUAL_CPC"


def _device_ctx(strategy: str):
    return _ctx(
        campaigns=[_campaign(campaign_id=1, bidding_strategy=strategy)],
        device_performance=[
            _device_perf(device="DESKTOP", cost_micros=10_000_000, conversions=50.0),
            _device_perf(device="MOBILE", cost_micros=20_000_000, conversions=5.0),
        ],
    )


def test_rule28_device_bid_suppressed_on_smart_bidding():
    assert DeviceBidAdjustmentRule().detect(_device_ctx(SMART)) == []
    assert len(DeviceBidAdjustmentRule().detect(_device_ctx(MANUAL))) == 1


def _hour_ctx(strategy: str):
    return _ctx(
        campaigns=[_campaign(campaign_id=1, bidding_strategy=strategy)],
        hour_performance=[_hour_perf()],  # default: 25M cost, 0 conversions → triggers
    )


def test_rule30_ad_schedule_suppressed_on_smart_bidding():
    assert AdScheduleAdjustmentRule().detect(_hour_ctx(SMART)) == []
    assert len(AdScheduleAdjustmentRule().detect(_hour_ctx(MANUAL))) >= 1


def _dow_ctx(strategy: str):
    return _ctx(
        campaigns=[_campaign(campaign_id=1, bidding_strategy=strategy)],
        history=_history(avg_cpa_micros=10_000_000, total_conv=100.0),
        day_of_week_performance=[
            _dow_perf(day_of_week="SUNDAY", cost_micros=200_000_000, conversions=10.0)
        ],
    )


def test_rule31_day_of_week_suppressed_on_smart_bidding():
    assert DayOfWeekBidAdjustmentRule().detect(_dow_ctx(SMART)) == []
    assert len(DayOfWeekBidAdjustmentRule().detect(_dow_ctx(MANUAL))) >= 1


def _redundancy_ctx(strategy: str):
    return _ctx(
        campaigns=[_campaign(campaign_id=1, bidding_strategy=strategy)],
        ad_groups=[_ad_group(ad_group_id=10, campaign_id=1)],
        keywords=[
            _keyword(criterion_id=1, ad_group_id=10, text="running shoes", match_type="BROAD"),
            _keyword(criterion_id=2, ad_group_id=10, text="running shoes", match_type="EXACT"),
        ],
    )


def test_rule27_match_type_redundancy_suppressed_on_smart_bidding():
    assert MatchTypeRedundancyRule().detect(_redundancy_ctx(SMART)) == []
    assert len(MatchTypeRedundancyRule().detect(_redundancy_ctx(MANUAL))) == 1


def _broad_ctx(strategy: str):
    terms = [
        _search_term(ad_group_id=10, search_term=f"unrelated topic {i}", cost_micros=1_000_000)
        for i in range(12)
    ]
    return _ctx(
        campaigns=[_campaign(campaign_id=1, bidding_strategy=strategy)],
        ad_groups=[_ad_group(ad_group_id=10, campaign_id=1)],
        keywords=[_keyword(criterion_id=1, ad_group_id=10, text="buty", match_type="BROAD")],
        search_terms=terms,
    )


def test_rule05_broad_match_suppressed_on_smart_bidding():
    assert BroadMatchBleedingRule().detect(_broad_ctx(SMART)) == []
    assert len(BroadMatchBleedingRule().detect(_broad_ctx(MANUAL))) == 1
