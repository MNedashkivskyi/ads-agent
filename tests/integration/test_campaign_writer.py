"""Integration tests for CampaignWriter against a real Google Ads test account.

These tests are SKIPPED by default.  To run them you must set the following
environment variables:

    GADS_TEST_CUSTOMER_ID  — e.g. "123-456-7890"
    GADS_TEST_REFRESH_TOKEN — OAuth2 refresh token for that account

The tests create a real campaign in PAUSED state, verify its structure, then
delete it cleanly.  They use the Google Ads test account type so no charges
are incurred.

Run with:
    uv run pytest tests/integration/test_campaign_writer.py -v -s
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.application.ports.campaign_writer import CreatedCampaignResources
from adcopilot.config import Settings
from adcopilot.domain.entities import AccountId
from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CampaignBriefId,
    CampaignProposal,
    CampaignProposalId,
    KeywordProposal,
    MatchType,
)
from adcopilot.infrastructure.google_ads.campaign_writer import CampaignWriter

# ---------------------------------------------------------------------------
# Skip markers
# ---------------------------------------------------------------------------

_CUSTOMER_ID = os.environ.get("GADS_TEST_CUSTOMER_ID", "")
_REFRESH_TOKEN = os.environ.get("GADS_TEST_REFRESH_TOKEN", "")

_skip_missing = pytest.mark.skipif(
    not _CUSTOMER_ID or not _REFRESH_TOKEN,
    reason=(
        "GADS_TEST_CUSTOMER_ID and GADS_TEST_REFRESH_TOKEN not set. "
        "Set these env vars to run integration tests against a real account."
    ),
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fake_settings() -> Settings:
    """Return a Settings instance using values from environment."""
    return Settings()  # type: ignore[call-arg]


def _fake_audit_repo() -> MagicMock:
    repo = MagicMock()
    repo.save = AsyncMock(return_value=None)
    return repo


def _make_test_proposal() -> CampaignProposal:
    """Build a minimal but valid proposal for integration testing."""
    brief_id = CampaignBriefId(str(uuid.uuid4()))
    run_id = uuid.uuid4().hex[:8]

    ag1 = AdGroupProposal(
        name=f"Integration Test AG1 {run_id}",
        keywords=[
            KeywordProposal(
                text=f"test keyword {i}",
                match_type=MatchType.PHRASE,
                estimated_cpc_micros=1_000_000,
            )
            for i in range(5)
        ],
        ads=[
            AdProposal(
                headlines=[
                    "Integration Test Ad",
                    "Test Headline Two",
                    "Test Headline Three",
                    "Headline Four Here",
                    "Headline Five Text",
                ],
                descriptions=[
                    "This is a test description for integration testing.",
                    "Second description line for integration test.",
                ],
                final_url="https://example.com/test",
                path_segments=("test", "ads"),
            )
        ],
    )

    return CampaignProposal(
        id=CampaignProposalId(str(uuid.uuid4())),
        brief_id=brief_id,
        campaign_name=f"Integration Test Campaign {run_id}",
        daily_budget_micros=10_000_000,  # 10 PLN/day
        location_targeting="Warsaw, PL",
        bidding_strategy="MAXIMIZE_CONVERSIONS",
        ad_groups=[ag1],
        negative_keywords=["free", "cheap"],
        estimated_cpc_range=(500_000, 2_000_000),
        generated_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@_skip_missing
class TestCampaignWriterIntegration:
    """Full create → verify → delete lifecycle against the Google Ads API."""

    @pytest.fixture
    def writer(self) -> CampaignWriter:
        return CampaignWriter(
            settings=_fake_settings(),
            audit_log_repo=_fake_audit_repo(),
            account_id=AccountId(_CUSTOMER_ID),
        )

    @pytest.mark.asyncio
    async def test_full_lifecycle_create_verify_delete(
        self, writer: CampaignWriter
    ) -> None:
        """Create a campaign with one ad group, verify PAUSED state, delete it."""
        proposal = _make_test_proposal()
        cid = _CUSTOMER_ID
        rt = _REFRESH_TOKEN

        resources: CreatedCampaignResources | None = None
        try:
            # Step 1 — create campaign + budget
            campaign_rn, budget_rn = await writer.create_campaign(cid, rt, proposal)
            assert campaign_rn, "campaign resource name should be non-empty"
            assert budget_rn, "budget resource name should be non-empty"
            print(f"\n  Campaign:  {campaign_rn}")
            print(f"  Budget:    {budget_rn}")

            # Step 2 — ad groups
            ag_rns = await writer.create_ad_groups(
                cid, rt, campaign_rn, proposal.ad_groups
            )
            assert len(ag_rns) == len(proposal.ad_groups)
            print(f"  AdGroups:  {ag_rns}")

            # Step 3 — keywords
            kw_rns: list[str] = []
            for ag_prop, ag_rn in zip(proposal.ad_groups, ag_rns):  # noqa: B905
                kws = await writer.create_keywords(cid, rt, ag_rn, ag_prop.keywords)
                kw_rns.extend(kws)
            assert len(kw_rns) == sum(len(ag.keywords) for ag in proposal.ad_groups)
            print(f"  Keywords:  {len(kw_rns)} created")

            # Step 4 — ads
            ad_rns: list[str] = []
            for ag_prop, ag_rn in zip(proposal.ad_groups, ag_rns):  # noqa: B905
                ads = await writer.create_ads(cid, rt, ag_rn, ag_prop.ads)
                ad_rns.extend(ads)
            assert len(ad_rns) == sum(len(ag.ads) for ag in proposal.ad_groups)
            print(f"  Ads:       {len(ad_rns)} created")

            # Step 5 — negative keywords
            neg_rns = await writer.create_negative_keywords(
                cid, rt, campaign_rn, proposal.negative_keywords
            )
            assert len(neg_rns) == len(proposal.negative_keywords)
            print(f"  Negatives: {len(neg_rns)} created")

            resources = CreatedCampaignResources(
                campaign_resource_name=campaign_rn,
                budget_resource_name=budget_rn,
                ad_group_resource_names=ag_rns,
                keyword_resource_names=kw_rns,
                ad_resource_names=ad_rns,
                negative_resource_names=neg_rns,
            )

        finally:
            # Always clean up — delete everything we created
            if resources is not None:
                print("\n  Cleaning up...")
                await writer.delete_draft_campaign(cid, rt, resources)
                print("  Cleanup complete.")
            elif "campaign_rn" in dir():
                # Partial creation — best effort cleanup
                partial = CreatedCampaignResources(
                    campaign_resource_name=locals().get("campaign_rn", ""),
                    budget_resource_name=locals().get("budget_rn", ""),
                    ad_group_resource_names=locals().get("ag_rns", []),
                    keyword_resource_names=locals().get("kw_rns", []),
                    ad_resource_names=locals().get("ad_rns", []),
                    negative_resource_names=[],
                )
                await writer.delete_draft_campaign(cid, rt, partial)

    @pytest.mark.asyncio
    async def test_enable_then_delete(self, writer: CampaignWriter) -> None:
        """Create campaign in PAUSED, enable it, then delete it."""
        proposal = _make_test_proposal()
        cid = _CUSTOMER_ID
        rt = _REFRESH_TOKEN

        campaign_rn, budget_rn = await writer.create_campaign(cid, rt, proposal)

        try:
            # Enable the campaign
            await writer.enable_campaign(cid, rt, campaign_rn)
            print(f"\n  Campaign {campaign_rn} enabled successfully")

        finally:
            resources = CreatedCampaignResources(
                campaign_resource_name=campaign_rn,
                budget_resource_name=budget_rn,
                ad_group_resource_names=[],
                keyword_resource_names=[],
                ad_resource_names=[],
                negative_resource_names=[],
            )
            await writer.delete_draft_campaign(cid, rt, resources)
            print("  Cleanup complete.")
