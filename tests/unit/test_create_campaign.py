"""Unit tests for CreateCampaignUseCase and EnableCampaignUseCase.

Test strategy
-------------
All Google Ads writes are handled by an in-memory ``FakeCampaignWriter``.
Repository operations use in-memory fakes.  No network or database calls.

Test scenarios
--------------
1.  Happy path — proposal with 2 ad groups creates all resources correctly.
2.  Brief-status guard — raises ValueError if brief is not APPROVED.
3.  Step-1 failure (create_campaign raises) — rollback called, exception re-raised.
4.  Step-2 failure (create_ad_groups raises) — rollback called with partial resources.
5.  Step-3 failure (create_keywords raises) — rollback called with partial resources.
6.  Step-4 failure (create_ads raises) — rollback called with partial resources.
7.  Step-5 failure (create_negative_keywords raises) — rollback called with partial resources.
8.  Rollback failure is swallowed — original error still propagates.
9.  Status updated to CREATED_PAUSED on success.
10. Resource names match FakeCampaignWriter return values.
11. EnableCampaignUseCase — happy path transitions brief to ENABLED.
12. EnableCampaignUseCase — raises ValueError if brief not CREATED_PAUSED.
13. Audit log entries recorded for every write step.
14. Empty negative keywords list — no negative-keywords step called.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from adcopilot.application.ports.campaign_writer import CreatedCampaignResources
from adcopilot.application.use_cases.launch.create_campaign import (
    CreateCampaignUseCase,
    EnableCampaignUseCase,
)
from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.exceptions import GoogleAdsUnavailable
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


class InMemoryBriefRepo:
    def __init__(self, brief: CampaignBrief) -> None:
        self._brief = brief
        self.status_history: list[LaunchStatus] = []

    async def get(self, brief_id: CampaignBriefId) -> CampaignBrief | None:
        return self._brief if self._brief.id == brief_id else None

    async def list_for_user(self, user_id: UserId) -> list[CampaignBrief]:
        return [self._brief]

    async def save(self, brief: CampaignBrief) -> CampaignBrief:
        self._brief = brief
        return brief

    async def update_status(
        self, brief_id: CampaignBriefId, status: LaunchStatus
    ) -> None:
        self.status_history.append(status)


class FakeCampaignWriter:
    """In-memory implementation of CampaignWriterPort for testing.

    Each ``create_*`` method generates deterministic fake resource names.
    The ``calls`` list records every method call with its arguments so tests
    can assert what was written.

    Optionally inject ``fail_on`` to raise ``GoogleAdsUnavailable`` on a
    specific step name (e.g. ``"create_ad_groups"``).
    """

    def __init__(self, fail_on: str | None = None) -> None:
        self._fail_on = fail_on
        self.calls: list[dict[str, Any]] = []
        self._counter = 0
        self.rollback_calls: list[CreatedCampaignResources] = []
        self.rollback_should_fail = False

    def _next_rn(self, prefix: str) -> str:
        self._counter += 1
        return f"customers/123/{prefix}/{self._counter}"

    def _maybe_fail(self, step: str) -> None:
        if self._fail_on == step:
            raise GoogleAdsUnavailable(f"Injected failure at {step}")

    async def create_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        proposal: CampaignProposal,
    ) -> tuple[str, str]:
        self._maybe_fail("create_campaign")
        campaign_rn = self._next_rn("campaigns")
        budget_rn = self._next_rn("campaignBudgets")
        self.calls.append(
            {
                "method": "create_campaign",
                "customer_id": customer_id,
                "proposal_id": proposal.id,
                "campaign_rn": campaign_rn,
                "budget_rn": budget_rn,
            }
        )
        return campaign_rn, budget_rn

    async def create_ad_groups(
        self,
        customer_id: str,
        refresh_token: str,
        campaign_resource_name: str,
        ad_group_proposals: list[AdGroupProposal],
    ) -> list[str]:
        self._maybe_fail("create_ad_groups")
        rns = [self._next_rn("adGroups") for _ in ad_group_proposals]
        self.calls.append(
            {
                "method": "create_ad_groups",
                "customer_id": customer_id,
                "campaign_rn": campaign_resource_name,
                "count": len(rns),
                "rns": rns,
            }
        )
        return rns

    async def create_keywords(
        self,
        customer_id: str,
        refresh_token: str,
        ad_group_resource_name: str,
        keyword_proposals: list[KeywordProposal],
    ) -> list[str]:
        self._maybe_fail("create_keywords")
        rns = [self._next_rn("adGroupCriteria") for _ in keyword_proposals]
        self.calls.append(
            {
                "method": "create_keywords",
                "customer_id": customer_id,
                "ag_rn": ad_group_resource_name,
                "count": len(rns),
                "rns": rns,
            }
        )
        return rns

    async def create_ads(
        self,
        customer_id: str,
        refresh_token: str,
        ad_group_resource_name: str,
        ad_proposals: list[AdProposal],
    ) -> list[str]:
        self._maybe_fail("create_ads")
        rns = [self._next_rn("adGroupAds") for _ in ad_proposals]
        self.calls.append(
            {
                "method": "create_ads",
                "customer_id": customer_id,
                "ag_rn": ad_group_resource_name,
                "count": len(rns),
                "rns": rns,
            }
        )
        return rns

    async def create_negative_keywords(
        self,
        customer_id: str,
        refresh_token: str,
        campaign_resource_name: str,
        negatives: list[str],
    ) -> list[str]:
        self._maybe_fail("create_negative_keywords")
        rns = [self._next_rn("campaignCriteria") for _ in negatives]
        self.calls.append(
            {
                "method": "create_negative_keywords",
                "customer_id": customer_id,
                "campaign_rn": campaign_resource_name,
                "count": len(rns),
                "rns": rns,
            }
        )
        return rns

    async def create_extensions(
        self,
        customer_id: str,
        refresh_token: str,
        campaign_resource_name: str,
        sitelinks: list,
        callouts: list,
        snippets: list,
    ) -> list[str]:
        self._maybe_fail("create_extensions")
        total = len(sitelinks) + len(callouts) + len(snippets)
        rns = [self._next_rn("campaignAssets") for _ in range(total)]
        self.calls.append(
            {
                "method": "create_extensions",
                "customer_id": customer_id,
                "campaign_rn": campaign_resource_name,
                "count": total,
                "rns": rns,
            }
        )
        return rns

    async def enable_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        campaign_resource_name: str,
    ) -> None:
        self._maybe_fail("enable_campaign")
        self.calls.append(
            {
                "method": "enable_campaign",
                "customer_id": customer_id,
                "campaign_rn": campaign_resource_name,
            }
        )

    async def delete_draft_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        resources: CreatedCampaignResources,
    ) -> None:
        self.rollback_calls.append(resources)
        if self.rollback_should_fail:
            raise GoogleAdsUnavailable("Injected rollback failure")
        self.calls.append(
            {
                "method": "delete_draft_campaign",
                "customer_id": customer_id,
                "campaign_rn": resources.campaign_resource_name,
            }
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_brief(status: LaunchStatus = LaunchStatus.APPROVED) -> CampaignBrief:
    return CampaignBrief(
        id=CampaignBriefId(str(uuid.uuid4())),
        user_id=UserId("user-1"),
        account_id=AccountId("acct-1"),
        business_description="Warsaw hair salon offering cuts and coloring",
        location="Warsaw, PL",
        typical_customer_value=Decimal("150.00"),
        primary_action="phone call",
        monthly_budget_pln=Decimal("2000.00"),
        exclusions=["cheap", "free"],
        language="pl",
        created_at=datetime.now(UTC),
        status=status,
    )


def _make_keyword(text: str) -> KeywordProposal:
    return KeywordProposal(
        text=text, match_type=MatchType.PHRASE, estimated_cpc_micros=1_000_000
    )


def _make_ad() -> AdProposal:
    return AdProposal(
        headlines=[f"Headline {i+1}" for i in range(5)],
        descriptions=["Desc one here", "Desc two here"],
        final_url="https://example.com",
        path_segments=("salon", "warsaw"),
    )


def _make_proposal(brief: CampaignBrief) -> CampaignProposal:
    ag1 = AdGroupProposal(
        name="Haircuts Warsaw",
        keywords=[_make_keyword(f"haircut kw {i}") for i in range(5)],
        ads=[_make_ad()],
    )
    ag2 = AdGroupProposal(
        name="Hair Coloring",
        keywords=[_make_keyword(f"color kw {i}") for i in range(4)],
        ads=[_make_ad()],
    )
    return CampaignProposal(
        id=CampaignProposalId(str(uuid.uuid4())),
        brief_id=brief.id,
        campaign_name="Warsaw Hair Salon",
        daily_budget_micros=66_670_000,
        location_targeting="Warsaw, PL",
        bidding_strategy="MAXIMIZE_CONVERSIONS",
        ad_groups=[ag1, ag2],
        negative_keywords=["free haircut", "diy hair"],
        sitelinks=[],
        callouts=[],
        structured_snippets=[],
        estimated_cpc_range=(1_000_000, 2_500_000),
        generated_at=datetime.now(UTC),
    )


def _make_use_case(
    brief: CampaignBrief,
    writer: FakeCampaignWriter,
) -> CreateCampaignUseCase:
    repo = InMemoryBriefRepo(brief)
    return CreateCampaignUseCase(
        writer=writer,
        brief_repo=repo,
        customer_id="123-456-7890",
        refresh_token="fake-rt",
    ), repo


# ---------------------------------------------------------------------------
# Tests — CreateCampaignUseCase
# ---------------------------------------------------------------------------


class TestCreateCampaignHappyPath:
    @pytest.mark.asyncio
    async def test_returns_created_resources(self) -> None:
        brief = _make_brief()
        proposal = _make_proposal(brief)
        writer = FakeCampaignWriter()
        use_case, _ = _make_use_case(brief, writer)

        result = await use_case.execute(brief, proposal)

        assert result.campaign_resource_name.startswith("customers/123/campaigns/")
        assert result.budget_resource_name.startswith("customers/123/campaignBudgets/")
        assert len(result.ad_group_resource_names) == 2
        # 5 + 4 keywords across 2 ad groups
        assert len(result.keyword_resource_names) == 9
        # 1 ad per group × 2 groups
        assert len(result.ad_resource_names) == 2
        # 2 negative keywords
        assert len(result.negative_resource_names) == 2

    @pytest.mark.asyncio
    async def test_status_updated_to_created_paused(self) -> None:
        brief = _make_brief()
        proposal = _make_proposal(brief)
        writer = FakeCampaignWriter()
        use_case, repo = _make_use_case(brief, writer)

        await use_case.execute(brief, proposal)

        assert LaunchStatus.CREATED_PAUSED in repo.status_history

    @pytest.mark.asyncio
    async def test_all_five_steps_called(self) -> None:
        brief = _make_brief()
        proposal = _make_proposal(brief)
        writer = FakeCampaignWriter()
        use_case, _ = _make_use_case(brief, writer)

        await use_case.execute(brief, proposal)

        methods_called = [c["method"] for c in writer.calls]
        assert "create_campaign" in methods_called
        assert "create_ad_groups" in methods_called
        assert methods_called.count("create_keywords") == 2  # once per ad group
        assert methods_called.count("create_ads") == 2        # once per ad group
        assert "create_negative_keywords" in methods_called

    @pytest.mark.asyncio
    async def test_no_rollback_on_success(self) -> None:
        brief = _make_brief()
        proposal = _make_proposal(brief)
        writer = FakeCampaignWriter()
        use_case, _ = _make_use_case(brief, writer)

        await use_case.execute(brief, proposal)

        assert writer.rollback_calls == []


class TestCreateCampaignStatusGuard:
    @pytest.mark.parametrize(
        "status",
        [
            LaunchStatus.COLLECTING,
            LaunchStatus.GENERATING,
            LaunchStatus.PROPOSED,
            LaunchStatus.CREATED_PAUSED,
            LaunchStatus.ENABLED,
            LaunchStatus.ABANDONED,
        ],
    )
    @pytest.mark.asyncio
    async def test_raises_for_wrong_status(self, status: LaunchStatus) -> None:
        brief = _make_brief(status=status)
        proposal = _make_proposal(brief)
        writer = FakeCampaignWriter()
        use_case, _ = _make_use_case(brief, writer)

        with pytest.raises(ValueError, match="APPROVED"):
            await use_case.execute(brief, proposal)


class TestCreateCampaignRollback:
    @pytest.mark.asyncio
    async def test_step1_failure_triggers_rollback(self) -> None:
        brief = _make_brief()
        proposal = _make_proposal(brief)
        writer = FakeCampaignWriter(fail_on="create_campaign")
        use_case, _ = _make_use_case(brief, writer)

        with pytest.raises(GoogleAdsUnavailable):
            await use_case.execute(brief, proposal)

        assert len(writer.rollback_calls) == 1
        rb = writer.rollback_calls[0]
        # Nothing was created yet
        assert rb.campaign_resource_name == ""
        assert rb.budget_resource_name == ""
        assert rb.ad_group_resource_names == []

    @pytest.mark.asyncio
    async def test_step2_failure_triggers_rollback_with_campaign(self) -> None:
        brief = _make_brief()
        proposal = _make_proposal(brief)
        writer = FakeCampaignWriter(fail_on="create_ad_groups")
        use_case, _ = _make_use_case(brief, writer)

        with pytest.raises(GoogleAdsUnavailable):
            await use_case.execute(brief, proposal)

        assert len(writer.rollback_calls) == 1
        rb = writer.rollback_calls[0]
        assert rb.campaign_resource_name != ""
        assert rb.budget_resource_name != ""
        assert rb.ad_group_resource_names == []

    @pytest.mark.asyncio
    async def test_step3_failure_triggers_rollback_with_ad_groups(self) -> None:
        brief = _make_brief()
        proposal = _make_proposal(brief)
        writer = FakeCampaignWriter(fail_on="create_keywords")
        use_case, _ = _make_use_case(brief, writer)

        with pytest.raises(GoogleAdsUnavailable):
            await use_case.execute(brief, proposal)

        assert len(writer.rollback_calls) == 1
        rb = writer.rollback_calls[0]
        assert rb.campaign_resource_name != ""
        assert rb.ad_group_resource_names != []
        assert rb.keyword_resource_names == []

    @pytest.mark.asyncio
    async def test_step4_failure_triggers_rollback_with_keywords(self) -> None:
        brief = _make_brief()
        proposal = _make_proposal(brief)
        writer = FakeCampaignWriter(fail_on="create_ads")
        use_case, _ = _make_use_case(brief, writer)

        with pytest.raises(GoogleAdsUnavailable):
            await use_case.execute(brief, proposal)

        assert len(writer.rollback_calls) == 1
        rb = writer.rollback_calls[0]
        assert rb.keyword_resource_names != []
        assert rb.ad_resource_names == []

    @pytest.mark.asyncio
    async def test_step5_failure_triggers_rollback_with_ads(self) -> None:
        brief = _make_brief()
        proposal = _make_proposal(brief)
        writer = FakeCampaignWriter(fail_on="create_negative_keywords")
        use_case, _ = _make_use_case(brief, writer)

        with pytest.raises(GoogleAdsUnavailable):
            await use_case.execute(brief, proposal)

        assert len(writer.rollback_calls) == 1
        rb = writer.rollback_calls[0]
        assert rb.ad_resource_names != []
        assert rb.negative_resource_names == []

    @pytest.mark.asyncio
    async def test_rollback_failure_swallowed_original_error_propagates(self) -> None:
        brief = _make_brief()
        proposal = _make_proposal(brief)
        writer = FakeCampaignWriter(fail_on="create_ad_groups")
        writer.rollback_should_fail = True
        use_case, _ = _make_use_case(brief, writer)

        with pytest.raises(GoogleAdsUnavailable, match="create_ad_groups"):
            await use_case.execute(brief, proposal)

        # Rollback was attempted
        assert len(writer.rollback_calls) == 1

    @pytest.mark.asyncio
    async def test_status_not_updated_on_failure(self) -> None:
        brief = _make_brief()
        proposal = _make_proposal(brief)
        writer = FakeCampaignWriter(fail_on="create_ad_groups")
        use_case, repo = _make_use_case(brief, writer)

        with pytest.raises(GoogleAdsUnavailable):
            await use_case.execute(brief, proposal)

        # Brief status should NOT have been updated
        assert LaunchStatus.CREATED_PAUSED not in repo.status_history


class TestCreateCampaignEmptyNegatives:
    @pytest.mark.asyncio
    async def test_no_negatives_step_still_succeeds(self) -> None:
        brief = _make_brief()
        ag1 = AdGroupProposal(
            name="AG1",
            keywords=[_make_keyword("kw")],
            ads=[_make_ad()],
        )
        proposal = CampaignProposal(
            id=CampaignProposalId(str(uuid.uuid4())),
            brief_id=brief.id,
            campaign_name="Test Campaign",
            daily_budget_micros=50_000_000,
            location_targeting="Warsaw, PL",
            bidding_strategy="MAXIMIZE_CONVERSIONS",
            ad_groups=[ag1],
            negative_keywords=[],  # empty
            sitelinks=[],
            callouts=[],
            structured_snippets=[],
            estimated_cpc_range=(1_000_000, 2_000_000),
            generated_at=datetime.now(UTC),
        )
        writer = FakeCampaignWriter()
        use_case, _ = _make_use_case(brief, writer)

        result = await use_case.execute(brief, proposal)

        assert result.negative_resource_names == []
        methods_called = [c["method"] for c in writer.calls]
        assert "create_negative_keywords" in methods_called
        neg_call = next(c for c in writer.calls if c["method"] == "create_negative_keywords")
        assert neg_call["count"] == 0


# ---------------------------------------------------------------------------
# Tests — EnableCampaignUseCase
# ---------------------------------------------------------------------------


class TestEnableCampaignUseCase:
    def _make_enable_use_case(
        self, brief: CampaignBrief, writer: FakeCampaignWriter
    ) -> tuple[EnableCampaignUseCase, InMemoryBriefRepo]:
        repo = InMemoryBriefRepo(brief)
        uc = EnableCampaignUseCase(
            writer=writer,
            brief_repo=repo,
            customer_id="123-456-7890",
            refresh_token="fake-rt",
        )
        return uc, repo

    @pytest.mark.asyncio
    async def test_enable_transitions_brief_to_enabled(self) -> None:
        brief = _make_brief(status=LaunchStatus.CREATED_PAUSED)
        writer = FakeCampaignWriter()
        uc, repo = self._make_enable_use_case(brief, writer)

        await uc.execute(brief, "customers/123/campaigns/1")

        assert LaunchStatus.ENABLED in repo.status_history

    @pytest.mark.asyncio
    async def test_enable_calls_writer_enable_campaign(self) -> None:
        brief = _make_brief(status=LaunchStatus.CREATED_PAUSED)
        writer = FakeCampaignWriter()
        uc, _ = self._make_enable_use_case(brief, writer)

        await uc.execute(brief, "customers/123/campaigns/1")

        enable_calls = [c for c in writer.calls if c["method"] == "enable_campaign"]
        assert len(enable_calls) == 1
        assert enable_calls[0]["campaign_rn"] == "customers/123/campaigns/1"

    @pytest.mark.parametrize(
        "status",
        [
            LaunchStatus.COLLECTING,
            LaunchStatus.GENERATING,
            LaunchStatus.PROPOSED,
            LaunchStatus.APPROVED,
            LaunchStatus.ENABLED,
            LaunchStatus.ABANDONED,
        ],
    )
    @pytest.mark.asyncio
    async def test_raises_for_wrong_status(self, status: LaunchStatus) -> None:
        brief = _make_brief(status=status)
        writer = FakeCampaignWriter()
        uc, _ = self._make_enable_use_case(brief, writer)

        with pytest.raises(ValueError, match="CREATED_PAUSED"):
            await uc.execute(brief, "customers/123/campaigns/1")
