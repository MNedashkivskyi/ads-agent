"""Tests for LLM model tiering (Tier-3 Phase 1)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from adcopilot.domain.launch.budget_tier import BudgetTier
from adcopilot.domain.launch.model_tier import model_for_tier

# --------------------------------------------------------------------------- #
# model_for_tier
# --------------------------------------------------------------------------- #


def test_growth_gets_premium():
    assert model_for_tier(BudgetTier.GROWTH, default="d", premium="p") == "p"


def test_non_growth_gets_default():
    assert model_for_tier(BudgetTier.MICRO, default="d", premium="p") == "d"
    assert model_for_tier(BudgetTier.MID, default="d", premium="p") == "d"


# --------------------------------------------------------------------------- #
# Generator routes ad copy to the premium client for GROWTH only
# --------------------------------------------------------------------------- #


_AD_COPY_JSON = json.dumps(
    {
        "variants": [
            {
                "headlines": ["Hook jeden", "Druga linia", "Trzecia"],
                "descriptions": ["Opis pierwszy wystarczająco długi.", "Opis drugi tutaj."],
                "path1": "salon",
                "path2": "",
            }
        ]
    }
)


class _RecordingLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, system, user, max_tokens=400, temperature=0.3):  # noqa: ARG002
        self.calls += 1
        return _AD_COPY_JSON


def _brief(budget: Decimal):
    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.domain.launch.entities import CampaignBrief, CampaignBriefId, LaunchStatus

    return CampaignBrief(
        id=CampaignBriefId(str(uuid.uuid4())),
        user_id=UserId(str(uuid.uuid4())),
        account_id=AccountId(str(uuid.uuid4())),
        business_description="Salon",
        location="Kraków",
        typical_customer_value=Decimal("150"),
        primary_action="phone_call",
        monthly_budget_pln=budget,
        exclusions=[],
        language="pl",
        created_at=datetime.now(UTC),
        status=LaunchStatus.COLLECTING,
    )


def _ad_group():
    from adcopilot.infrastructure.llm.campaign_generator import AdGroupItem, KeywordItem

    return AdGroupItem(
        name="g",
        theme="t",
        keywords=[KeywordItem(text="a"), KeywordItem(text="b"), KeywordItem(text="c")],
    )


@pytest.mark.asyncio
async def test_growth_ad_copy_uses_premium_client():
    from adcopilot.infrastructure.llm.campaign_generator import CampaignGenerator

    default_llm, premium_llm = _RecordingLLM(), _RecordingLLM()
    gen = CampaignGenerator(default_llm, premium_llm=premium_llm)

    await gen.generate_ad_copy(_ad_group(), _brief(Decimal("5000")))  # GROWTH

    assert premium_llm.calls == 1
    assert default_llm.calls == 0


@pytest.mark.asyncio
async def test_micro_ad_copy_uses_default_client():
    from adcopilot.infrastructure.llm.campaign_generator import CampaignGenerator

    default_llm, premium_llm = _RecordingLLM(), _RecordingLLM()
    gen = CampaignGenerator(default_llm, premium_llm=premium_llm)

    await gen.generate_ad_copy(_ad_group(), _brief(Decimal("300")))  # MICRO

    assert default_llm.calls == 1
    assert premium_llm.calls == 0


@pytest.mark.asyncio
async def test_no_premium_client_falls_back_to_default():
    from adcopilot.infrastructure.llm.campaign_generator import CampaignGenerator

    default_llm = _RecordingLLM()
    gen = CampaignGenerator(default_llm)  # no premium configured

    await gen.generate_ad_copy(_ad_group(), _brief(Decimal("5000")))  # GROWTH

    assert default_llm.calls == 1
