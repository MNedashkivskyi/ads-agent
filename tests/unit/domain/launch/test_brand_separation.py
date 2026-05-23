"""Unit tests for brand campaign separation (Task 4.1)."""
from datetime import UTC, datetime
from decimal import Decimal

from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.launch.entities import CampaignBrief, CampaignBriefId, LaunchStatus
from adcopilot.domain.launch.templates import build_proposal_from_template


def _make_brief(monthly_budget_pln: Decimal) -> CampaignBrief:
    return CampaignBrief(
        id=CampaignBriefId("test-brief-1"),
        user_id=UserId("user-1"),
        account_id=AccountId("acc-1"),
        business_description="Kancelaria prawna Kowalski adwokat Warszawa",
        location="Warsaw, Poland",
        typical_customer_value=Decimal("5000"),
        primary_action="Call",
        monthly_budget_pln=monthly_budget_pln,
        exclusions=[],
        language="pl",
        created_at=datetime.now(UTC),
        status=LaunchStatus.COLLECTING,
        interview_step=0,
        campaign_resource_name=None,
    )


def test_micro_tier_no_brand_campaign():
    brief = _make_brief(Decimal("300"))  # MICRO
    proposal = build_proposal_from_template(brief)
    assert proposal.brand_campaign_name is None
    assert proposal.brand_keywords == []
    assert proposal.brand_daily_budget_micros == 0
    assert proposal.brand_ad is None


def test_mid_tier_has_brand_campaign():
    brief = _make_brief(Decimal("1000"))  # MID
    proposal = build_proposal_from_template(brief)
    assert proposal.brand_campaign_name is not None
    assert "Brand Search" in proposal.brand_campaign_name
    assert len(proposal.brand_keywords) >= 1
    assert proposal.brand_daily_budget_micros > 0
    assert proposal.brand_ad is not None


def test_growth_tier_has_brand_campaign():
    brief = _make_brief(Decimal("5000"))  # GROWTH
    proposal = build_proposal_from_template(brief)
    assert proposal.brand_campaign_name is not None
    assert proposal.brand_daily_budget_micros > 0


def test_brand_budget_is_10_percent_of_daily():
    brief = _make_brief(Decimal("1000"))  # MID
    proposal = build_proposal_from_template(brief)
    expected_daily = int(Decimal("1000") / Decimal("30") * Decimal("1000000"))
    expected_brand = max(1, int(expected_daily * 0.1))
    assert proposal.brand_daily_budget_micros == expected_brand


def test_brand_keywords_are_exact_match():
    from adcopilot.domain.launch.entities import MatchType
    brief = _make_brief(Decimal("1000"))  # MID
    proposal = build_proposal_from_template(brief)
    for kw in proposal.brand_keywords:
        assert kw.match_type == MatchType.EXACT


def test_proposal_post_init_sets_empty_brand_keywords():
    """CampaignProposal.__post_init__ sets brand_keywords=[] if None."""
    from datetime import UTC, datetime

    from adcopilot.domain.launch.entities import (
        CampaignBriefId,
        CampaignProposal,
        CampaignProposalId,
    )
    proposal = CampaignProposal(
        id=CampaignProposalId("p1"),
        brief_id=CampaignBriefId("b1"),
        campaign_name="Test",
        daily_budget_micros=1000000,
        location_targeting="Warsaw",
        bidding_strategy="MAXIMIZE_CLICKS",
        ad_groups=[],
        negative_keywords=[],
        sitelinks=[],
        callouts=[],
        structured_snippets=[],
        estimated_cpc_range=(500000, 2000000),
        generated_at=datetime.now(UTC),
    )
    assert proposal.brand_keywords == []
    assert proposal.brand_campaign_name is None
