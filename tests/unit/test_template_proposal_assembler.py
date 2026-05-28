"""Unit and integration tests for TemplateProposalAssembler (Task 1.4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from adcopilot.application.detection.validation import (
    LandingPageCheckResult,
    ValidationContext,
    validate_proposal,
)
from adcopilot.application.services.template_proposal_assembler import TemplateProposalAssembler
from adcopilot.domain.launch.budget_tier import BudgetTier
from adcopilot.domain.launch.entities import (
    CampaignBrief,
    CampaignBriefId,
    LaunchStatus,
)
from adcopilot.domain.entities import AccountId, UserId
from adcopilot.infrastructure.vertical_templates.yaml_adapter import YamlVerticalTemplateAdapter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VERTICAL_IDS = [
    "beauty_salon",
    "dental_clinic",
    "law_firm",
    "restaurant",
    "auto_repair",
    "cleaning_service",
    "generic",
]

BUDGET_TIERS = [
    ("micro", Decimal("400")),    # MICRO: < 500
    ("mid", Decimal("1200")),     # MID: 500-2999
    ("growth", Decimal("5000")),  # GROWTH: >= 3000
]


@pytest.fixture(scope="module")
def adapter() -> YamlVerticalTemplateAdapter:
    return YamlVerticalTemplateAdapter()


@pytest.fixture(scope="module")
def assembler() -> TemplateProposalAssembler:
    return TemplateProposalAssembler()


def _make_brief(monthly_budget: Decimal, city: str = "Warszawa") -> CampaignBrief:
    return CampaignBrief(
        id=CampaignBriefId(str(uuid.uuid4())),
        user_id=UserId(str(uuid.uuid4())),
        account_id=AccountId(str(uuid.uuid4())),
        business_description="Profesjonalny salon urody w centrum miasta",
        location=city,
        typical_customer_value=Decimal("200"),
        primary_action="phone_call",
        monthly_budget_pln=monthly_budget,
        exclusions=[],
        language="pl",
        created_at=datetime.now(UTC),
        status=LaunchStatus.COLLECTING,
    )


# ---------------------------------------------------------------------------
# Core acceptance tests
# ---------------------------------------------------------------------------

class TestBeautySalonMidBudget:
    """Task 1.4 acceptance criteria: beauty_salon + Warszawa + 1200 PLN → MID."""

    def test_has_expected_ad_groups(self, adapter, assembler):
        template = adapter.get_template("beauty_salon")
        brief = _make_brief(Decimal("1200"))
        proposal = assembler.assemble(template, brief)
        assert len(proposal.ad_groups) >= 3

    def test_mid_tier_bidding(self, adapter, assembler):
        template = adapter.get_template("beauty_salon")
        brief = _make_brief(Decimal("1200"))
        proposal = assembler.assemble(template, brief)
        cfg = template.bidding_defaults.for_tier("mid")
        assert proposal.bidding_strategy == cfg.bidding_strategy

    def test_location_targeting(self, adapter, assembler):
        template = adapter.get_template("beauty_salon")
        brief = _make_brief(Decimal("1200"), city="Warszawa")
        proposal = assembler.assemble(template, brief)
        assert "Warszawa" in proposal.location_targeting

    def test_micro_fewer_keywords_than_growth(self, adapter, assembler):
        template = adapter.get_template("beauty_salon")
        brief_micro = _make_brief(Decimal("400"))
        brief_growth = _make_brief(Decimal("5000"))
        p_micro = assembler.assemble(template, brief_micro)
        p_growth = assembler.assemble(template, brief_growth)
        micro_kws = sum(len(ag.keywords) for ag in p_micro.ad_groups)
        growth_kws = sum(len(ag.keywords) for ag in p_growth.ad_groups)
        assert micro_kws < growth_kws

    def test_city_placeholder_resolved(self, adapter, assembler):
        template = adapter.get_template("beauty_salon")
        brief = _make_brief(Decimal("1200"), city="Kraków")
        proposal = assembler.assemble(template, brief)
        for ag in proposal.ad_groups:
            assert "{city}" not in ag.name
            for kw in ag.keywords:
                assert "{city}" not in kw.text

    def test_phone_added_to_callouts(self, adapter, assembler):
        template = adapter.get_template("beauty_salon")
        brief = _make_brief(Decimal("1200"))
        proposal = assembler.assemble(template, brief, phone="+48 123 456 789")
        callout_texts = [c.text for c in proposal.callouts]
        assert any("+48" in t for t in callout_texts)


# ---------------------------------------------------------------------------
# 21-combination validation matrix (7 templates × 3 budget tiers)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("vertical_id", VERTICAL_IDS)
@pytest.mark.parametrize("tier_name,budget", BUDGET_TIERS)
class TestAllCombinationsPassValidation:
    def test_proposal_passes_all_validation_rules(
        self, vertical_id, tier_name, budget, adapter, assembler
    ):
        template = (
            adapter.get_default_template()
            if vertical_id == "generic"
            else adapter.get_template(vertical_id)
        )
        assert template is not None, f"Template '{vertical_id}' not found"

        brief = _make_brief(budget)
        proposal = assembler.assemble(template, brief)

        lp_result = LandingPageCheckResult(
            url="https://example.com",
            reachable=True,
            https=True,
            load_time_seconds=0.5,
            language_detected="pl",
        )
        ctx = ValidationContext(
            has_conversion_tracking=True,
            landing_page_results={"https://example.com": lp_result},
        )
        result = validate_proposal(proposal, brief, ctx)

        assert result.passed, (
            f"Proposal for {vertical_id}/{tier_name} failed validation:\n"
            + "\n".join(f"  - {e}" for e in result.errors)
        )

    def test_keyword_count_per_group_within_limits(
        self, vertical_id, tier_name, budget, adapter, assembler
    ):
        template = (
            adapter.get_default_template()
            if vertical_id == "generic"
            else adapter.get_template(vertical_id)
        )
        brief = _make_brief(budget)
        proposal = assembler.assemble(template, brief)

        for ag in proposal.ad_groups:
            assert 3 <= len(ag.keywords) <= 15, (
                f"{vertical_id}/{tier_name}: ad group '{ag.name}' has "
                f"{len(ag.keywords)} keywords (must be 3–15)"
            )

    def test_ad_copy_within_character_limits(
        self, vertical_id, tier_name, budget, adapter, assembler
    ):
        template = (
            adapter.get_default_template()
            if vertical_id == "generic"
            else adapter.get_template(vertical_id)
        )
        brief = _make_brief(budget)
        proposal = assembler.assemble(template, brief)

        for ag in proposal.ad_groups:
            for ad in ag.ads:
                assert len(ad.headlines) >= 3
                for h in ad.headlines:
                    assert len(h) <= 30, f"Headline too long: '{h}'"
                assert len(ad.descriptions) >= 2
                for d in ad.descriptions:
                    assert len(d) <= 90, f"Description too long: '{d}'"
                for seg in ad.path_segments:
                    assert len(seg) <= 15, f"Path segment too long: '{seg}'"

    def test_standard_negatives_included(
        self, vertical_id, tier_name, budget, adapter, assembler
    ):
        from adcopilot.domain.polish_market.negative_keywords import POLISH_STANDARD_NEGATIVES
        template = (
            adapter.get_default_template()
            if vertical_id == "generic"
            else adapter.get_template(vertical_id)
        )
        brief = _make_brief(budget)
        proposal = assembler.assemble(template, brief)
        neg_lower = [n.lower() for n in proposal.negative_keywords]

        for category, terms in POLISH_STANDARD_NEGATIVES:
            covered = any(any(t in neg for t in terms) for neg in neg_lower)
            assert covered, (
                f"{vertical_id}/{tier_name}: missing standard negative category '{category}'"
            )
