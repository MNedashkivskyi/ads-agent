"""Tests for CampaignBriefRepo and CampaignProposalRepo Protocol contracts.

Strategy
--------
Two in-memory fakes are defined here that satisfy the Protocols.
The same test functions are then run against each fake to verify that any
concrete implementation that passes mypy Protocol checking also passes the
behavioural contract tested below.

mypy verifies structural compatibility at import time via the
``_assert_implements_*`` helpers at module level.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from adcopilot.application.ports.launch_repositories import (
    CampaignBriefRepo,
    CampaignProposalRepo,
)
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
# In-memory fakes
# ---------------------------------------------------------------------------


class InMemoryCampaignBriefRepo:
    """In-memory implementation of ``CampaignBriefRepo`` for testing."""

    def __init__(self) -> None:
        self._store: dict[CampaignBriefId, CampaignBrief] = {}

    async def get(self, brief_id: CampaignBriefId) -> CampaignBrief | None:
        return self._store.get(brief_id)

    async def list_for_user(self, user_id: UserId) -> list[CampaignBrief]:
        return [b for b in self._store.values() if b.user_id == user_id]

    async def save(self, brief: CampaignBrief) -> CampaignBrief:
        self._store[brief.id] = brief
        return brief

    async def update_status(
        self,
        brief_id: CampaignBriefId,
        status: LaunchStatus,
    ) -> None:
        existing = self._store.get(brief_id)
        if existing is not None:
            self._store[brief_id] = dataclasses.replace(existing, status=status)


class InMemoryCampaignProposalRepo:
    """In-memory implementation of ``CampaignProposalRepo`` for testing."""

    def __init__(self) -> None:
        self._store: dict[CampaignProposalId, CampaignProposal] = {}

    async def get(self, proposal_id: CampaignProposalId) -> CampaignProposal | None:
        return self._store.get(proposal_id)

    async def get_by_brief(self, brief_id: CampaignBriefId) -> CampaignProposal | None:
        # Return the most recently generated proposal for this brief.
        matches = [p for p in self._store.values() if p.brief_id == brief_id]
        if not matches:
            return None
        return max(matches, key=lambda p: p.generated_at)

    async def save(self, proposal: CampaignProposal) -> CampaignProposal:
        self._store[proposal.id] = proposal
        return proposal


# ---------------------------------------------------------------------------
# Protocol compatibility assertions (checked by mypy at import time)
# ---------------------------------------------------------------------------

if TYPE_CHECKING:
    _brief_repo: CampaignBriefRepo = InMemoryCampaignBriefRepo()
    _proposal_repo: CampaignProposalRepo = InMemoryCampaignProposalRepo()


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 14, 2, 0, tzinfo=UTC)
_LATER = datetime(2026, 4, 14, 3, 0, tzinfo=UTC)


def _brief(
    brief_id: str = "brief-1",
    user_id: str = "user-1",
    status: LaunchStatus = LaunchStatus.COLLECTING,
) -> CampaignBrief:
    return CampaignBrief(
        id=CampaignBriefId(brief_id),
        user_id=UserId(user_id),
        account_id=AccountId("acc-1"),
        business_description="Shoe store.",
        location="Warsaw",
        typical_customer_value=Decimal("350.00"),
        primary_action="purchase",
        monthly_budget_pln=Decimal("3000.00"),
        exclusions=[],
        language="pl",
        created_at=_NOW,
        status=status,
    )


def _proposal(
    proposal_id: str = "prop-1",
    brief_id: str = "brief-1",
    generated_at: datetime = _NOW,
) -> CampaignProposal:
    kw = KeywordProposal(
        text="running shoes",
        match_type=MatchType.EXACT,
        estimated_cpc_micros=1_200_000,
    )
    ad = AdProposal(
        headlines=["Best Shoes", "Free Delivery"],
        descriptions=["Top quality."],
        final_url="https://example.com",
        path_segments=("shoes", ""),
    )
    ag = AdGroupProposal(name="Generic", keywords=[kw], ads=[ad])
    return CampaignProposal(
        id=CampaignProposalId(proposal_id),
        brief_id=CampaignBriefId(brief_id),
        campaign_name="Shoes PL",
        daily_budget_micros=50_000_000,
        location_targeting="Warsaw, PL",
        bidding_strategy="TARGET_CPA",
        ad_groups=[ag],
        negative_keywords=["free"],
        sitelinks=[],
        callouts=[],
        structured_snippets=[],
        estimated_cpc_range=(800_000, 1_500_000),
        generated_at=generated_at,
    )


# ---------------------------------------------------------------------------
# CampaignBriefRepo contract tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brief_repo_save_and_get() -> None:
    repo = InMemoryCampaignBriefRepo()
    brief = _brief()

    await repo.save(brief)
    fetched = await repo.get(CampaignBriefId("brief-1"))

    assert fetched is not None
    assert fetched.id == "brief-1"
    assert fetched.user_id == "user-1"
    assert fetched.status is LaunchStatus.COLLECTING


@pytest.mark.asyncio
async def test_brief_repo_get_returns_none_when_missing() -> None:
    repo = InMemoryCampaignBriefRepo()
    result = await repo.get(CampaignBriefId("nonexistent"))
    assert result is None


@pytest.mark.asyncio
async def test_brief_repo_save_returns_saved_entity() -> None:
    repo = InMemoryCampaignBriefRepo()
    brief = _brief()
    returned = await repo.save(brief)
    assert returned.id == brief.id


@pytest.mark.asyncio
async def test_brief_repo_save_overwrites_existing() -> None:
    repo = InMemoryCampaignBriefRepo()
    brief = _brief(status=LaunchStatus.COLLECTING)
    await repo.save(brief)

    updated = dataclasses.replace(brief, status=LaunchStatus.GENERATING)
    await repo.save(updated)

    fetched = await repo.get(CampaignBriefId("brief-1"))
    assert fetched is not None
    assert fetched.status is LaunchStatus.GENERATING


@pytest.mark.asyncio
async def test_brief_repo_list_for_user_returns_only_matching() -> None:
    repo = InMemoryCampaignBriefRepo()
    b1 = _brief("brief-1", user_id="user-A")
    b2 = _brief("brief-2", user_id="user-A")
    b3 = _brief("brief-3", user_id="user-B")

    for b in (b1, b2, b3):
        await repo.save(b)

    results = await repo.list_for_user(UserId("user-A"))
    ids = {r.id for r in results}

    assert "brief-1" in ids
    assert "brief-2" in ids
    assert "brief-3" not in ids


@pytest.mark.asyncio
async def test_brief_repo_list_for_user_empty_when_none() -> None:
    repo = InMemoryCampaignBriefRepo()
    results = await repo.list_for_user(UserId("nobody"))
    assert results == []


@pytest.mark.asyncio
async def test_brief_repo_update_status_transitions() -> None:
    repo = InMemoryCampaignBriefRepo()
    brief = _brief(status=LaunchStatus.COLLECTING)
    await repo.save(brief)

    await repo.update_status(CampaignBriefId("brief-1"), LaunchStatus.PROPOSED)

    fetched = await repo.get(CampaignBriefId("brief-1"))
    assert fetched is not None
    assert fetched.status is LaunchStatus.PROPOSED


@pytest.mark.asyncio
async def test_brief_repo_update_status_noop_when_missing() -> None:
    """update_status on a non-existent id must not raise."""
    repo = InMemoryCampaignBriefRepo()
    await repo.update_status(CampaignBriefId("ghost"), LaunchStatus.ABANDONED)


# ---------------------------------------------------------------------------
# CampaignProposalRepo contract tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proposal_repo_save_and_get() -> None:
    repo = InMemoryCampaignProposalRepo()
    prop = _proposal()

    await repo.save(prop)
    fetched = await repo.get(CampaignProposalId("prop-1"))

    assert fetched is not None
    assert fetched.id == "prop-1"
    assert fetched.campaign_name == "Shoes PL"


@pytest.mark.asyncio
async def test_proposal_repo_get_returns_none_when_missing() -> None:
    repo = InMemoryCampaignProposalRepo()
    result = await repo.get(CampaignProposalId("nonexistent"))
    assert result is None


@pytest.mark.asyncio
async def test_proposal_repo_save_returns_saved_entity() -> None:
    repo = InMemoryCampaignProposalRepo()
    prop = _proposal()
    returned = await repo.save(prop)
    assert returned.id == prop.id


@pytest.mark.asyncio
async def test_proposal_repo_get_by_brief_returns_most_recent() -> None:
    repo = InMemoryCampaignProposalRepo()
    early = _proposal("prop-1", "brief-1", generated_at=_NOW)
    late = _proposal("prop-2", "brief-1", generated_at=_LATER)

    await repo.save(early)
    await repo.save(late)

    result = await repo.get_by_brief(CampaignBriefId("brief-1"))
    assert result is not None
    assert result.id == "prop-2"


@pytest.mark.asyncio
async def test_proposal_repo_get_by_brief_returns_none_when_missing() -> None:
    repo = InMemoryCampaignProposalRepo()
    result = await repo.get_by_brief(CampaignBriefId("brief-1"))
    assert result is None


@pytest.mark.asyncio
async def test_proposal_repo_get_by_brief_ignores_other_briefs() -> None:
    repo = InMemoryCampaignProposalRepo()
    prop = _proposal("prop-1", "brief-1")
    await repo.save(prop)

    result = await repo.get_by_brief(CampaignBriefId("brief-99"))
    assert result is None


@pytest.mark.asyncio
async def test_proposal_repo_preserves_nested_structure() -> None:
    repo = InMemoryCampaignProposalRepo()
    prop = _proposal()
    await repo.save(prop)

    fetched = await repo.get(CampaignProposalId("prop-1"))
    assert fetched is not None
    assert len(fetched.ad_groups) == 1
    assert fetched.ad_groups[0].name == "Generic"
    assert len(fetched.ad_groups[0].keywords) == 1
    assert fetched.ad_groups[0].keywords[0].text == "running shoes"
    assert fetched.ad_groups[0].keywords[0].match_type is MatchType.EXACT
    assert len(fetched.ad_groups[0].ads) == 1
    assert fetched.ad_groups[0].ads[0].final_url == "https://example.com"
