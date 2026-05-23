"""CreateCampaignUseCase — orchestrate the full Google Ads campaign-creation flow.

The use case calls the five write steps in order:

  1. create_campaign          — CampaignBudget + Campaign (PAUSED)
  2. create_ad_groups         — one AdGroup per AdGroupProposal
  3. create_keywords          — AdGroupCriterion keywords per ad group
  4. create_ads               — RSA per ad group
  5. create_negative_keywords — campaign-level negatives

If any step raises, every resource created up to that point is deleted via
``delete_draft_campaign`` so no orphan resources are left in the customer
account (transactional best-effort rollback).

``enable_campaign`` is NOT called here; it is a separate, explicit use case
triggered only after a second user confirmation.
"""

from __future__ import annotations

import structlog

from adcopilot.application.ports.campaign_writer import (
    CampaignWriterPort,
    CreatedCampaignResources,
)
from adcopilot.application.ports.launch_repositories import CampaignBriefRepo
from adcopilot.domain.exceptions import GoogleAdsAuthError, GoogleAdsUnavailable
from adcopilot.domain.launch.entities import (
    CampaignBrief,
    CampaignProposal,
    LaunchStatus,
)

logger = structlog.get_logger(__name__)


class CreateCampaignUseCase:
    """Write the full campaign structure to Google Ads, then update brief status.

    Parameters
    ----------
    writer:
        ``CampaignWriterPort`` implementation (real or fake).
    brief_repo:
        Repository used to update brief status after creation.
    customer_id:
        Google Ads customer account ID (with or without dashes).
    refresh_token:
        OAuth2 refresh token for the customer's Google account.
    """

    def __init__(
        self,
        writer: CampaignWriterPort,
        brief_repo: CampaignBriefRepo,
        customer_id: str,
        refresh_token: str,
    ) -> None:
        self._writer = writer
        self._brief_repo = brief_repo
        self._customer_id = customer_id
        self._refresh_token = refresh_token

    async def execute(
        self,
        brief: CampaignBrief,
        proposal: CampaignProposal,
    ) -> CreatedCampaignResources:
        """Create every resource in Google Ads; return the created resource names.

        Status transitions
        ------------------
        APPROVED → CREATED_PAUSED   (success path)
        APPROVED → APPROVED          (rolled back on failure — status unchanged)

        Raises
        ------
        ValueError
            If *brief* is not in APPROVED status.
        GoogleAdsAuthError | GoogleAdsUnavailable
            After rollback, if the Google Ads API raised an error.
        """
        if brief.status != LaunchStatus.APPROVED:
            raise ValueError(
                f"Cannot create campaign for brief {brief.id} "
                f"in status {brief.status!r} — expected APPROVED"
            )

        cid = self._customer_id
        rt = self._refresh_token

        # Track what we've created for atomic rollback
        campaign_rn = ""
        budget_rn = ""
        ad_group_rns: list[str] = []
        keyword_rns: list[str] = []
        ad_rns: list[str] = []
        negative_rns: list[str] = []

        try:
            # Step 1 — Campaign + Budget
            campaign_rn, budget_rn = await self._writer.create_campaign(cid, rt, proposal)
            logger.info(
                "create_campaign_step_done",
                brief_id=brief.id,
                campaign_rn=campaign_rn,
            )

            # Step 2 — Ad Groups
            ad_group_rns = await self._writer.create_ad_groups(
                cid, rt, campaign_rn, proposal.ad_groups
            )
            logger.info(
                "create_ad_groups_step_done",
                brief_id=brief.id,
                count=len(ad_group_rns),
            )

            # Step 3 — Keywords (per ad group, sequential)
            for ag_proposal, ag_rn in zip(proposal.ad_groups, ad_group_rns):  # noqa: B905
                kw_rns = await self._writer.create_keywords(cid, rt, ag_rn, ag_proposal.keywords)
                keyword_rns.extend(kw_rns)
            logger.info(
                "create_keywords_step_done",
                brief_id=brief.id,
                total_keywords=len(keyword_rns),
            )

            # Step 4 — Ads (per ad group, sequential)
            for ag_proposal, ag_rn in zip(proposal.ad_groups, ad_group_rns):  # noqa: B905
                a_rns = await self._writer.create_ads(cid, rt, ag_rn, ag_proposal.ads)
                ad_rns.extend(a_rns)
            logger.info(
                "create_ads_step_done",
                brief_id=brief.id,
                total_ads=len(ad_rns),
            )

            # Step 5 — Campaign-level negative keywords
            negative_rns = await self._writer.create_negative_keywords(
                cid, rt, campaign_rn, proposal.negative_keywords
            )
            logger.info(
                "create_negatives_step_done",
                brief_id=brief.id,
                count=len(negative_rns),
            )

        except (GoogleAdsAuthError, GoogleAdsUnavailable, Exception) as exc:
            logger.error(
                "campaign_creation_failed_rolling_back",
                brief_id=brief.id,
                error=str(exc),
            )
            resources_so_far = CreatedCampaignResources(
                campaign_resource_name=campaign_rn,
                budget_resource_name=budget_rn,
                ad_group_resource_names=ad_group_rns,
                keyword_resource_names=keyword_rns,
                ad_resource_names=ad_rns,
                negative_resource_names=negative_rns,
            )
            try:
                await self._writer.delete_draft_campaign(cid, rt, resources_so_far)
            except Exception as rollback_exc:
                logger.error(
                    "rollback_failed",
                    brief_id=brief.id,
                    error=str(rollback_exc),
                )
            raise

        resources = CreatedCampaignResources(
            campaign_resource_name=campaign_rn,
            budget_resource_name=budget_rn,
            ad_group_resource_names=ad_group_rns,
            keyword_resource_names=keyword_rns,
            ad_resource_names=ad_rns,
            negative_resource_names=negative_rns,
        )

        # Update brief status
        await self._brief_repo.update_status(brief.id, LaunchStatus.CREATED_PAUSED)
        logger.info(
            "campaign_created_paused",
            brief_id=brief.id,
            campaign_rn=campaign_rn,
            total_ad_groups=len(ad_group_rns),
            total_keywords=len(keyword_rns),
            total_ads=len(ad_rns),
        )

        return resources


class EnableCampaignUseCase:
    """Transition a PAUSED campaign to ENABLED after explicit second confirmation.

    Parameters
    ----------
    writer:
        ``CampaignWriterPort`` implementation.
    brief_repo:
        Repository used to update brief status.
    customer_id:
        Google Ads customer account ID.
    refresh_token:
        OAuth2 refresh token for the customer's Google account.
    """

    def __init__(
        self,
        writer: CampaignWriterPort,
        brief_repo: CampaignBriefRepo,
        customer_id: str,
        refresh_token: str,
    ) -> None:
        self._writer = writer
        self._brief_repo = brief_repo
        self._customer_id = customer_id
        self._refresh_token = refresh_token

    async def execute(
        self,
        brief: CampaignBrief,
        campaign_resource_name: str,
    ) -> None:
        """Enable the campaign and update brief status to ENABLED.

        Raises
        ------
        ValueError
            If *brief* is not in CREATED_PAUSED status.
        """
        if brief.status != LaunchStatus.CREATED_PAUSED:
            raise ValueError(
                f"Cannot enable campaign for brief {brief.id} "
                f"in status {brief.status!r} — expected CREATED_PAUSED"
            )

        await self._writer.enable_campaign(
            self._customer_id, self._refresh_token, campaign_resource_name
        )
        await self._brief_repo.update_status(brief.id, LaunchStatus.ENABLED)
        logger.info(
            "campaign_enabled",
            brief_id=brief.id,
            campaign_rn=campaign_resource_name,
        )
