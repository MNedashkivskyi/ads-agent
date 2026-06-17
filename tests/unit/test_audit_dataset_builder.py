"""Unit tests for build_audit_dataset (Audit Funnel T2.1, pure mapper)."""

from __future__ import annotations

from datetime import date

from adcopilot.application.audit.dataset_builder import build_audit_dataset
from adcopilot.application.audit.scan_reader import AuditRawData
from adcopilot.domain.snapshot import (
    CampaignSnapshot,
    ConversionActionSnapshot,
    KeywordSnapshot,
    SearchTermSnapshot,
)

_D = date(2026, 5, 31)
_M = 1_000_000


def _campaign(cost: int, *, budget_lost_is: float | None = None) -> CampaignSnapshot:
    return CampaignSnapshot(
        id="c",
        account_id="acc",
        snapshot_date=_D,
        campaign_id=1,
        name="C",
        status="ENABLED",
        channel_type="SEARCH",
        budget_micros=100 * _M,
        bidding_strategy="MANUAL_CPC",
        impressions=1000,
        clicks=100,
        cost_micros=cost,
        conversions=0.0,
        conv_value=0.0,
        search_budget_lost_impression_share=budget_lost_is,
    )


def _term(
    term: str, *, clicks: int, conv: float, cost: int, matched: int | None = None
) -> SearchTermSnapshot:
    return SearchTermSnapshot(
        id="t",
        account_id="acc",
        snapshot_date=_D,
        search_term=term,
        ad_group_id=1,
        impressions=clicks * 10,
        clicks=clicks,
        cost_micros=cost,
        conversions=conv,
        matched_keyword_id=matched,
    )


def _keyword(text: str, *, criterion_id: int) -> KeywordSnapshot:
    return KeywordSnapshot(
        id="k",
        account_id="acc",
        snapshot_date=_D,
        criterion_id=criterion_id,
        ad_group_id=1,
        text=text,
        match_type="BROAD",
        status="ENABLED",
        quality_score=None,
        impressions=200,
        clicks=20,
        cost_micros=80 * _M,
        conversions=0.0,
        ctr=0.1,
        avg_cpc_micros=0,
    )


def _conv_action(*, status: str = "ENABLED", counted: bool = True) -> ConversionActionSnapshot:
    return ConversionActionSnapshot(
        id="ca",
        account_id="acc",
        snapshot_date=_D,
        conversion_action_id=1,
        name="Purchase",
        category="PURCHASE",
        counting_type="ONE_PER_CLICK",
        status=status,
        include_in_conversions_metric=counted,
    )


def test_builder_maps_dedups_and_flags_gap_and_issues() -> None:
    raw = AuditRawData(
        campaigns=[
            _campaign(300 * _M, budget_lost_is=0.2),
            _campaign(200 * _M, budget_lost_is=0.05),
        ],
        search_terms=[_term("za darmo x", clicks=10, conv=0, cost=50 * _M, matched=99)],
        keywords=[_keyword("buty", criterion_id=99)],
        conversion_actions=[],  # no tracking -> measurement gap
    )
    ds = build_audit_dataset(raw, window_start=date(2026, 5, 1), window_end=_D, days=30)
    assert ds.total_spend_micros == 500 * _M
    assert ds.search_terms[0].matched_keyword == "buty"  # criterion id 99 resolved to text
    assert ds.measurement_gap_pct == 1.0
    assert ds.issues_count == 1  # only the campaign above the 10% budget-lost threshold
    assert ds.days_of_data == 30


def test_builder_no_gap_when_tracking_present() -> None:
    raw = AuditRawData(
        campaigns=[_campaign(100 * _M)],
        search_terms=[],
        keywords=[],
        conversion_actions=[_conv_action()],
    )
    ds = build_audit_dataset(raw, window_start=date(2026, 5, 1), window_end=_D, days=30)
    assert ds.measurement_gap_pct == 0.0


def test_builder_gap_when_conversion_action_disabled() -> None:
    raw = AuditRawData(
        campaigns=[_campaign(100 * _M)],
        search_terms=[],
        keywords=[],
        conversion_actions=[_conv_action(status="REMOVED")],
    )
    ds = build_audit_dataset(raw, window_start=date(2026, 5, 1), window_end=_D, days=30)
    assert ds.measurement_gap_pct == 1.0
