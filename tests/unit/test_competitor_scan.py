"""Tests for the launch-time competitor scan (Tier-2 Phase 3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from adcopilot.domain.competitors import CompetitorShare, top_competitors
from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.launch.entities import CampaignBrief, CampaignBriefId, LaunchStatus
from adcopilot.infrastructure.llm.campaign_generator import (
    VerticalClassification,
    _structure_user_prompt,
)

# --------------------------------------------------------------------------- #
# top_competitors aggregation
# --------------------------------------------------------------------------- #


def test_top_competitors_takes_max_share_per_domain_sorted_desc():
    rows = [
        {"competitor_domain": "a.pl", "impression_share": 0.30},
        {"competitor_domain": "a.pl", "impression_share": 0.55},  # max wins
        {"competitor_domain": "b.pl", "impression_share": 0.40},
    ]
    out = top_competitors(rows)
    assert out == [
        CompetitorShare(domain="a.pl", impression_share=0.55),
        CompetitorShare(domain="b.pl", impression_share=0.40),
    ]


def test_top_competitors_limit_and_skips_empty_domain():
    rows = [{"competitor_domain": "", "impression_share": 0.9}] + [
        {"competitor_domain": f"d{i}.pl", "impression_share": i / 10} for i in range(1, 8)
    ]
    out = top_competitors(rows, limit=3)
    assert len(out) == 3
    assert [c.domain for c in out] == ["d7.pl", "d6.pl", "d5.pl"]


def test_top_competitors_empty_rows():
    assert top_competitors([]) == []


# --------------------------------------------------------------------------- #
# Prompt threading
# --------------------------------------------------------------------------- #


def _brief() -> CampaignBrief:
    return CampaignBrief(
        id=CampaignBriefId(str(uuid.uuid4())),
        user_id=UserId(str(uuid.uuid4())),
        account_id=AccountId(str(uuid.uuid4())),
        business_description="Salon kosmetyczny",
        location="Kraków",
        typical_customer_value=Decimal("150"),
        primary_action="phone_call",
        monthly_budget_pln=Decimal("1200"),
        exclusions=[],
        language="pl",
        created_at=datetime.now(UTC),
        status=LaunchStatus.COLLECTING,
    )


def _vertical() -> VerticalClassification:
    return VerticalClassification(vertical="salon", competitive_level="medium", language_hint="pl")


def test_structure_prompt_includes_competitors_when_present():
    prompt = _structure_user_prompt(
        _brief(),
        _vertical(),
        "MAXIMIZE_CONVERSIONS",
        competitors=[
            CompetitorShare(domain="rival.pl", impression_share=0.42),
            CompetitorShare(domain="other.pl", impression_share=0.20),
        ],
    )
    assert "rival.pl" in prompt
    assert "42%" in prompt
    assert "competitors" in prompt.lower()


def test_structure_prompt_omits_competitor_line_when_absent():
    prompt = _structure_user_prompt(_brief(), _vertical(), "MAXIMIZE_CONVERSIONS")
    assert "competitors already bidding" not in prompt.lower()
