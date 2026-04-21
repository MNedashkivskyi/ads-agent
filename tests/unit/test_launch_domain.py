"""Unit tests for adcopilot.domain.launch entities.

Verifies:
- All entities are frozen (field reassignment raises FrozenInstanceError)
- Enum values round-trip correctly
- NewType IDs behave as str
- Nested structures compose without error
- No framework imports anywhere in the domain package
"""

from __future__ import annotations

import dataclasses
import importlib
import pkgutil
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CampaignBrief,
    CampaignBriefId,
    CampaignProposal,
    CampaignProposalId,
    KeywordProposal,
    LaunchStatus,
    MatchType,
)

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 14, 2, 0, tzinfo=UTC)


def make_keyword(**kwargs: object) -> KeywordProposal:
    defaults: dict[str, object] = {
        "text": "buy running shoes",
        "match_type": MatchType.EXACT,
        "estimated_cpc_micros": 1_500_000,
    }
    defaults.update(kwargs)
    return KeywordProposal(**defaults)  # type: ignore[arg-type]


def make_ad(**kwargs: object) -> AdProposal:
    defaults: dict[str, object] = {
        "headlines": ["Best Running Shoes", "Free Delivery Today", "Shop Now"],
        "descriptions": ["Top brands in stock.", "Order before midnight."],
        "final_url": "https://example.com/shoes",
        "path_segments": ("shoes", "sale"),
    }
    defaults.update(kwargs)
    return AdProposal(**defaults)  # type: ignore[arg-type]


def make_ad_group(**kwargs: object) -> AdGroupProposal:
    defaults: dict[str, object] = {
        "name": "Running Shoes",
        "keywords": [make_keyword()],
        "ads": [make_ad()],
    }
    defaults.update(kwargs)
    return AdGroupProposal(**defaults)  # type: ignore[arg-type]


def make_proposal(**kwargs: object) -> CampaignProposal:
    defaults: dict[str, object] = {
        "id": CampaignProposalId("prop-1"),
        "brief_id": CampaignBriefId("brief-1"),
        "campaign_name": "Running Shoes PL",
        "daily_budget_micros": 50_000_000,
        "location_targeting": "Warsaw, PL",
        "bidding_strategy": "TARGET_CPA",
        "ad_groups": [make_ad_group()],
        "negative_keywords": ["free", "cheap"],
        "sitelinks": [],
        "callouts": [],
        "structured_snippets": [],
        "estimated_cpc_range": (800_000, 2_000_000),
        "generated_at": _NOW,
    }
    defaults.update(kwargs)
    return CampaignProposal(**defaults)  # type: ignore[arg-type]


def make_brief(**kwargs: object) -> CampaignBrief:
    defaults: dict[str, object] = {
        "id": CampaignBriefId("brief-1"),
        "user_id": UserId("user-1"),
        "account_id": AccountId("acc-1"),
        "business_description": "Online running shoe retailer.",
        "location": "Warsaw",
        "typical_customer_value": Decimal("350.00"),
        "primary_action": "purchase",
        "monthly_budget_pln": Decimal("3000.00"),
        "exclusions": ["wholesale", "distributor"],
        "language": "pl",
        "created_at": _NOW,
        "status": LaunchStatus.COLLECTING,
    }
    defaults.update(kwargs)
    return CampaignBrief(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# LaunchStatus enum
# ---------------------------------------------------------------------------


def test_launch_status_values() -> None:
    assert LaunchStatus.COLLECTING.value == "collecting"
    assert LaunchStatus.GENERATING.value == "generating"
    assert LaunchStatus.PROPOSED.value == "proposed"
    assert LaunchStatus.APPROVED.value == "approved"
    assert LaunchStatus.CREATED_PAUSED.value == "created_paused"
    assert LaunchStatus.ENABLED.value == "enabled"
    assert LaunchStatus.ABANDONED.value == "abandoned"


def test_launch_status_is_str() -> None:
    for member in LaunchStatus:
        assert isinstance(member, str)


def test_launch_status_round_trips_from_string() -> None:
    assert LaunchStatus("proposed") is LaunchStatus.PROPOSED
    assert LaunchStatus("enabled") is LaunchStatus.ENABLED


# ---------------------------------------------------------------------------
# MatchType enum
# ---------------------------------------------------------------------------


def test_match_type_values() -> None:
    assert MatchType.BROAD.value == "broad"
    assert MatchType.PHRASE.value == "phrase"
    assert MatchType.EXACT.value == "exact"


# ---------------------------------------------------------------------------
# CampaignBriefId / CampaignProposalId are str
# ---------------------------------------------------------------------------


def test_campaign_brief_id_is_str() -> None:
    bid = CampaignBriefId("abc-123")
    assert isinstance(bid, str)
    assert bid == "abc-123"


def test_campaign_proposal_id_is_str() -> None:
    pid = CampaignProposalId("prop-xyz")
    assert isinstance(pid, str)


# ---------------------------------------------------------------------------
# KeywordProposal
# ---------------------------------------------------------------------------


def test_keyword_proposal_frozen() -> None:
    kw = make_keyword()
    with pytest.raises(dataclasses.FrozenInstanceError):
        kw.text = "other"  # type: ignore[misc]


def test_keyword_proposal_fields() -> None:
    kw = make_keyword(text="running trainers", match_type=MatchType.BROAD, estimated_cpc_micros=500_000)
    assert kw.text == "running trainers"
    assert kw.match_type is MatchType.BROAD
    assert kw.estimated_cpc_micros == 500_000


# ---------------------------------------------------------------------------
# AdProposal
# ---------------------------------------------------------------------------


def test_ad_proposal_frozen() -> None:
    ad = make_ad()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ad.final_url = "https://other.com"  # type: ignore[misc]


def test_ad_proposal_path_segments() -> None:
    ad = make_ad(path_segments=("shoes", "running"))
    assert ad.path_segments == ("shoes", "running")
    assert len(ad.path_segments) == 2


def test_ad_proposal_headlines_and_descriptions() -> None:
    headlines = ["H1", "H2", "H3"]
    descs = ["D1", "D2"]
    ad = make_ad(headlines=headlines, descriptions=descs)
    assert ad.headlines == ["H1", "H2", "H3"]
    assert ad.descriptions == ["D1", "D2"]


# ---------------------------------------------------------------------------
# AdGroupProposal
# ---------------------------------------------------------------------------


def test_ad_group_proposal_frozen() -> None:
    ag = make_ad_group()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ag.name = "Other"  # type: ignore[misc]


def test_ad_group_proposal_contains_keywords_and_ads() -> None:
    kw = make_keyword(text="trail running shoes")
    ad = make_ad()
    ag = make_ad_group(keywords=[kw], ads=[ad])
    assert len(ag.keywords) == 1
    assert ag.keywords[0].text == "trail running shoes"
    assert len(ag.ads) == 1


# ---------------------------------------------------------------------------
# CampaignProposal
# ---------------------------------------------------------------------------


def test_campaign_proposal_frozen() -> None:
    prop = make_proposal()
    with pytest.raises(dataclasses.FrozenInstanceError):
        prop.campaign_name = "Other"  # type: ignore[misc]


def test_campaign_proposal_cpc_range() -> None:
    prop = make_proposal(estimated_cpc_range=(1_000_000, 3_000_000))
    lo, hi = prop.estimated_cpc_range
    assert lo == 1_000_000
    assert hi == 3_000_000
    assert lo <= hi


def test_campaign_proposal_has_ad_groups() -> None:
    ag1 = make_ad_group(name="Group A")
    ag2 = make_ad_group(name="Group B")
    prop = make_proposal(ad_groups=[ag1, ag2])
    assert len(prop.ad_groups) == 2
    assert prop.ad_groups[0].name == "Group A"


def test_campaign_proposal_negative_keywords() -> None:
    prop = make_proposal(negative_keywords=["free", "cheap", "wholesale"])
    assert "free" in prop.negative_keywords
    assert len(prop.negative_keywords) == 3


# ---------------------------------------------------------------------------
# CampaignBrief
# ---------------------------------------------------------------------------


def test_campaign_brief_frozen() -> None:
    brief = make_brief()
    with pytest.raises(dataclasses.FrozenInstanceError):
        brief.status = LaunchStatus.APPROVED  # type: ignore[misc]


def test_campaign_brief_monetary_fields_are_decimal() -> None:
    brief = make_brief(
        typical_customer_value=Decimal("250.50"),
        monthly_budget_pln=Decimal("1500.00"),
    )
    assert isinstance(brief.typical_customer_value, Decimal)
    assert isinstance(brief.monthly_budget_pln, Decimal)
    assert brief.typical_customer_value == Decimal("250.50")
    assert brief.monthly_budget_pln == Decimal("1500.00")


def test_campaign_brief_exclusions() -> None:
    brief = make_brief(exclusions=["wholesale", "jobs", "salary"])
    assert "jobs" in brief.exclusions
    assert len(brief.exclusions) == 3


def test_campaign_brief_default_status() -> None:
    brief = make_brief(status=LaunchStatus.COLLECTING)
    assert brief.status is LaunchStatus.COLLECTING


def test_campaign_brief_user_and_account_ids() -> None:
    brief = make_brief()
    assert isinstance(brief.user_id, str)
    assert isinstance(brief.account_id, str)


# ---------------------------------------------------------------------------
# No forbidden framework imports in the launch domain package
# ---------------------------------------------------------------------------


def test_domain_has_no_fastapi_imports() -> None:
    """The launch domain package must not import FastAPI, SQLAlchemy, or google.ads."""
    import adcopilot.domain.launch as pkg

    forbidden = ("fastapi", "sqlalchemy", "google.ads")
    pkg_path = pkg.__path__

    for _, module_name, _ in pkgutil.walk_packages(
        path=pkg_path, prefix=pkg.__name__ + "."
    ):
        mod = importlib.import_module(module_name)
        for attr in dir(mod):
            if attr.startswith("__"):
                continue
        # Check the module's source by inspecting its __spec__.origin
        import inspect

        try:
            source = inspect.getsource(mod)
        except (OSError, TypeError):
            continue

        for banned in forbidden:
            assert banned not in source, (
                f"Module {module_name} contains a forbidden import: {banned!r}"
            )
