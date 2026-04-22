"""PMaxCampaignWriter — Google Ads API adapter for Performance Max campaign creation.

Creates the PMax campaign structure from a ``PMaxCampaignProposal``:

  1. create_pmax_campaign:
       a. CampaignBudget (shared)
       b. Campaign (PERFORMANCE_MAX, PAUSED)
       c. AssetGroup(s) with text assets (headlines + descriptions)
       d. ListingGroupFilter (all products — catch-all)
       e. AudienceSignal(s) for the asset group (best-effort)

  2. enable_pmax_campaign — transitions campaign from PAUSED to ENABLED.

  3. delete_draft_pmax_campaign — removes all created resources on error
     (rollback).

Note: image assets must be uploaded separately by the client (GCS path) and
are not created here. Headlines/descriptions are TEXT_ASSET type.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from adcopilot.application.ports.campaign_writer import CreatedPMaxResources
from adcopilot.config import Settings
from adcopilot.domain.exceptions import GoogleAdsAuthError, GoogleAdsUnavailable
from adcopilot.domain.launch.entities import PMaxCampaignProposal
from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter, is_google_auth_error

logger = structlog.get_logger(__name__)

_CAMPAIGN_WRITE_REC_ID = "00000000-0000-0000-0000-000000000000"


def _wrap_exc(exc: Exception) -> Exception:
    if is_google_auth_error(exc):
        return GoogleAdsAuthError(str(exc))
    error_str = str(exc).lower()
    if "quota" in error_str or "resource exhausted" in error_str:
        from adcopilot.domain.exceptions import GoogleAdsRateLimited
        return GoogleAdsRateLimited(str(exc))
    return GoogleAdsUnavailable(str(exc))


class PMaxCampaignWriter:
    """Google Ads API adapter for creating Performance Max campaigns."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _build_client(self, refresh_token: str) -> GoogleAdsClientAdapter:
        return GoogleAdsClientAdapter(
            refresh_token=refresh_token,
            settings=self._settings,
        )

    async def create_pmax_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        proposal: PMaxCampaignProposal,
    ) -> CreatedPMaxResources:
        """Create PMax budget, campaign, and asset groups. Returns all resource names.

        Rolls back (deletes) on any failure.
        """
        adapter = self._build_client(refresh_token)
        budget_rn: str | None = None
        campaign_rn: str | None = None
        asset_group_rns: list[str] = []

        try:
            # 1. CampaignBudget
            budget_rn = await self._create_budget(adapter, customer_id, proposal)
            logger.info("pmax: budget created", resource=budget_rn)

            # 2. Campaign (PERFORMANCE_MAX, PAUSED)
            campaign_rn = await self._create_campaign(
                adapter, customer_id, proposal, budget_rn
            )
            logger.info("pmax: campaign created", resource=campaign_rn)

            # 3. AssetGroups with text assets + listing group filter
            for ag in proposal.asset_groups:
                ag_rn = await self._create_asset_group(
                    adapter, customer_id, campaign_rn, ag, proposal.merchant_center_feed_id
                )
                asset_group_rns.append(ag_rn)
                logger.info("pmax: asset group created", resource=ag_rn)

            # 4. Audience signals (best-effort — do not fail the whole flow)
            if proposal.audience_signals:
                for ag_rn in asset_group_rns:
                    try:
                        await self._add_audience_signals(
                            adapter, customer_id, ag_rn, proposal.audience_signals
                        )
                    except Exception as exc:
                        logger.warning(
                            "pmax: audience signal failed (non-fatal)",
                            error=str(exc),
                            asset_group=ag_rn,
                        )

            return CreatedPMaxResources(
                campaign_resource_name=campaign_rn,
                budget_resource_name=budget_rn,
                asset_group_resource_names=asset_group_rns,
            )

        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            await self._rollback(adapter, customer_id, campaign_rn, budget_rn, asset_group_rns)
            raise
        except Exception as exc:
            await self._rollback(adapter, customer_id, campaign_rn, budget_rn, asset_group_rns)
            raise _wrap_exc(exc) from exc

    async def _create_budget(
        self,
        adapter: GoogleAdsClientAdapter,
        customer_id: str,
        proposal: PMaxCampaignProposal,
    ) -> str:
        client = adapter.client
        budget_service = client.get_service("CampaignBudgetService")
        campaign_budget_operation = client.get_type("CampaignBudgetOperation")
        budget = campaign_budget_operation.create
        budget.name = f"PMax Budget – {proposal.campaign_name} – {uuid.uuid4().hex[:8]}"
        budget.amount_micros = proposal.daily_budget_micros
        budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
        budget.explicitly_shared = False

        response = budget_service.mutate_campaign_budgets(
            customer_id=customer_id,
            operations=[campaign_budget_operation],
        )
        return response.results[0].resource_name

    async def _create_campaign(
        self,
        adapter: GoogleAdsClientAdapter,
        customer_id: str,
        proposal: PMaxCampaignProposal,
        budget_resource_name: str,
    ) -> str:
        client = adapter.client
        campaign_service = client.get_service("CampaignService")
        campaign_operation = client.get_type("CampaignOperation")
        campaign = campaign_operation.create
        campaign.name = proposal.campaign_name
        campaign.advertising_channel_type = (
            client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
        )
        campaign.status = client.enums.CampaignStatusEnum.PAUSED
        campaign.campaign_budget = budget_resource_name
        campaign.bidding_strategy_type = (
            client.enums.BiddingStrategyTypeEnum.MAXIMIZE_CONVERSIONS
        )
        # Link to Merchant Center (shopping_setting)
        campaign.shopping_setting.merchant_id = proposal.merchant_center_feed_id

        response = campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[campaign_operation],
        )
        return response.results[0].resource_name

    async def _create_asset_group(
        self,
        adapter: GoogleAdsClientAdapter,
        customer_id: str,
        campaign_resource_name: str,
        ag_proposal: Any,
        merchant_center_feed_id: int,
    ) -> str:
        client = adapter.client
        asset_group_service = client.get_service("AssetGroupService")

        # Build text assets (headlines + descriptions)
        asset_operations = []
        asset_resource_names = []
        asset_service = client.get_service("AssetService")

        for headline in ag_proposal.headlines:
            op = client.get_type("AssetOperation")
            op.create.text_asset.text = headline
            asset_operations.append(op)

        for description in ag_proposal.descriptions:
            op = client.get_type("AssetOperation")
            op.create.text_asset.text = description
            asset_operations.append(op)

        if asset_operations:
            asset_response = asset_service.mutate_assets(
                customer_id=customer_id, operations=asset_operations
            )
            asset_resource_names = [r.resource_name for r in asset_response.results]

        # Create AssetGroup
        ag_op = client.get_type("AssetGroupOperation")
        ag = ag_op.create
        ag.name = ag_proposal.name
        ag.campaign = campaign_resource_name
        ag.final_urls.append(ag_proposal.final_url)
        ag.status = client.enums.AssetGroupStatusEnum.ENABLED

        ag_response = asset_group_service.mutate_asset_groups(
            customer_id=customer_id, operations=[ag_op]
        )
        ag_resource_name = ag_response.results[0].resource_name

        # Link assets to the asset group
        if asset_resource_names:
            link_service = client.get_service("AssetGroupAssetService")
            link_ops = []
            n_headlines = len(ag_proposal.headlines)
            for i, rn in enumerate(asset_resource_names):
                link_op = client.get_type("AssetGroupAssetOperation")
                link = link_op.create
                link.asset_group = ag_resource_name
                link.asset = rn
                link.field_type = (
                    client.enums.AssetFieldTypeEnum.HEADLINE
                    if i < n_headlines
                    else client.enums.AssetFieldTypeEnum.DESCRIPTION
                )
                link_ops.append(link_op)
            link_service.mutate_asset_group_assets(
                customer_id=customer_id, operations=link_ops
            )

        # Add catch-all listing group filter (all products)
        lg_service = client.get_service("AssetGroupListingGroupFilterService")
        lg_op = client.get_type("AssetGroupListingGroupFilterOperation")
        lg = lg_op.create
        lg.asset_group = ag_resource_name
        lg.type_ = client.enums.ListingGroupFilterTypeEnum.UNIT_INCLUDED
        lg_service.mutate_asset_group_listing_group_filters(
            customer_id=customer_id, operations=[lg_op]
        )

        return ag_resource_name

    async def _add_audience_signals(
        self,
        adapter: GoogleAdsClientAdapter,
        customer_id: str,
        asset_group_resource_name: str,
        audience_signal_resource_names: list[str],
    ) -> None:
        client = adapter.client
        signal_service = client.get_service("AssetGroupSignalService")
        ops = []
        for rn in audience_signal_resource_names:
            op = client.get_type("AssetGroupSignalOperation")
            signal = op.create
            signal.asset_group = asset_group_resource_name
            signal.audience.audience = rn
            ops.append(op)
        if ops:
            signal_service.mutate_asset_group_signals(
                customer_id=customer_id, operations=ops
            )

    async def _rollback(
        self,
        adapter: GoogleAdsClientAdapter,
        customer_id: str,
        campaign_rn: str | None,
        budget_rn: str | None,
        asset_group_rns: list[str],
    ) -> None:
        """Best-effort cleanup — log but do not re-raise."""
        client = adapter.client
        try:
            if asset_group_rns:
                ag_service = client.get_service("AssetGroupService")
                ag_ops = []
                for rn in asset_group_rns:
                    op = client.get_type("AssetGroupOperation")
                    op.remove = rn
                    ag_ops.append(op)
                ag_service.mutate_asset_groups(customer_id=customer_id, operations=ag_ops)
        except Exception as exc:
            logger.warning("pmax rollback: asset group removal failed", error=str(exc))

        try:
            if campaign_rn:
                c_service = client.get_service("CampaignService")
                c_op = client.get_type("CampaignOperation")
                c_op.remove = campaign_rn
                c_service.mutate_campaigns(customer_id=customer_id, operations=[c_op])
        except Exception as exc:
            logger.warning("pmax rollback: campaign removal failed", error=str(exc))

        try:
            if budget_rn:
                b_service = client.get_service("CampaignBudgetService")
                b_op = client.get_type("CampaignBudgetOperation")
                b_op.remove = budget_rn
                b_service.mutate_campaign_budgets(customer_id=customer_id, operations=[b_op])
        except Exception as exc:
            logger.warning("pmax rollback: budget removal failed", error=str(exc))

    async def enable_pmax_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        campaign_resource_name: str,
    ) -> None:
        """Enable a PAUSED PMax campaign."""
        adapter = self._build_client(refresh_token)
        client = adapter.client
        campaign_service = client.get_service("CampaignService")
        op = client.get_type("CampaignOperation")
        campaign = op.update
        campaign.resource_name = campaign_resource_name
        campaign.status = client.enums.CampaignStatusEnum.ENABLED
        field_mask = client.get_type("FieldMask")
        field_mask.paths.append("status")
        op.update_mask.CopyFrom(field_mask)
        campaign_service.mutate_campaigns(customer_id=customer_id, operations=[op])

    async def delete_draft_pmax_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        resources: CreatedPMaxResources,
    ) -> None:
        """Remove all PMax resources — used for explicit user-initiated rollback."""
        adapter = self._build_client(refresh_token)
        await self._rollback(
            adapter,
            customer_id,
            resources.campaign_resource_name,
            resources.budget_resource_name,
            resources.asset_group_resource_names,
        )
