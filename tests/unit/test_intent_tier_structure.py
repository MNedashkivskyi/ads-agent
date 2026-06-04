"""Tests for brand/non-brand + intent-tier campaign structure (Tier-2 Phase 4)."""

from __future__ import annotations

from pathlib import Path

from adcopilot.infrastructure.llm.campaign_generator import (
    _STRUCTURE_SYSTEM,
    AdGroupItem,
    KeywordItem,
)

# --------------------------------------------------------------------------- #
# AdGroupItem schema: intent_tier normalization + is_brand
# --------------------------------------------------------------------------- #


def _ag(**kw) -> AdGroupItem:
    base = dict(
        name="g",
        theme="t",
        keywords=[KeywordItem(text="a"), KeywordItem(text="b"), KeywordItem(text="c")],
    )
    base.update(kw)
    return AdGroupItem(**base)


def test_intent_tier_normalized_variants():
    assert _ag(intent_tier="high-intent").intent_tier == "HIGH_INTENT"
    assert _ag(intent_tier="mid intent").intent_tier == "MID_INTENT"
    assert _ag(intent_tier="DISCOVERY").intent_tier == "DISCOVERY"


def test_invalid_intent_tier_becomes_none():
    assert _ag(intent_tier="whatever").intent_tier is None


def test_intent_tier_and_is_brand_default():
    ag = _ag()
    assert ag.intent_tier is None
    assert ag.is_brand is False


def test_is_brand_accepted():
    assert _ag(is_brand=True).is_brand is True


# --------------------------------------------------------------------------- #
# Prompt: instructs intent tiers + brand exclusion; parity with seeded migration
# --------------------------------------------------------------------------- #


def test_structure_system_prompt_mentions_intent_and_brand():
    assert "intent_tier" in _STRUCTURE_SYSTEM
    assert "HIGH_INTENT" in _STRUCTURE_SYSTEM
    assert "is_brand" in _STRUCTURE_SYSTEM
    assert "brand" in _STRUCTURE_SYSTEM.lower()


def test_structure_prompt_matches_seeded_migration_v2():
    import importlib.util

    mig = (
        Path(__file__).resolve().parents[2]
        / "adcopilot/infrastructure/db/alembic/versions/0069_seed_launch_structure_v2_prompt.py"
    )
    spec = importlib.util.spec_from_file_location("mig0069", mig)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._CONTENT == _STRUCTURE_SYSTEM
    assert mod._VERSION == 2


# --------------------------------------------------------------------------- #
# Assembly threads intent_tier (ad group → keywords) + is_brand
# --------------------------------------------------------------------------- #


def test_assemble_threads_intent_tier_and_brand():
    import uuid
    from datetime import UTC, datetime
    from decimal import Decimal

    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.domain.launch.entities import (
        CampaignBrief,
        CampaignBriefId,
        LaunchStatus,
    )
    from adcopilot.infrastructure.llm.campaign_generator import (
        AdGroupCopyResponse,
        CampaignGenerator,
        CampaignStructureResponse,
        NegativeKeywordsResponse,
        RSAVariantItem,
    )

    brief = CampaignBrief(
        id=CampaignBriefId(str(uuid.uuid4())),
        user_id=UserId(str(uuid.uuid4())),
        account_id=AccountId(str(uuid.uuid4())),
        business_description="Salon",
        location="Kraków",
        typical_customer_value=Decimal("150"),
        primary_action="phone_call",
        monthly_budget_pln=Decimal("1200"),
        exclusions=[],
        language="pl",
        created_at=datetime.now(UTC),
        status=LaunchStatus.COLLECTING,
    )
    structure = CampaignStructureResponse(
        campaign_name="Camp",
        bidding_strategy="MAXIMIZE_CONVERSIONS",
        ad_groups=[
            AdGroupItem(
                name="Booking",
                theme="booking",
                intent_tier="high-intent",
                is_brand=False,
                keywords=[
                    KeywordItem(text="rezerwacja salon"),
                    KeywordItem(text="umów wizytę"),
                    KeywordItem(text="salon cennik"),
                ],
            )
        ],
    )
    copies = [
        AdGroupCopyResponse(
            variants=[RSAVariantItem(headlines=["a", "b", "c"], descriptions=["dd", "ee"])]
        )
    ]
    gen = CampaignGenerator(llm=None)  # assemble_proposal does not call the LLM
    proposal = gen.assemble_proposal(
        brief,
        structure,
        copies,
        NegativeKeywordsResponse(keywords=[]),
        None,
        None,
    )
    ag = proposal.ad_groups[0]
    assert ag.intent_tier == "HIGH_INTENT"
    assert ag.is_brand is False
    assert all(kw.intent_tier == "HIGH_INTENT" for kw in ag.keywords)
