"""CampaignWriter — Google Ads API adapter for full campaign creation.

Creates the complete campaign structure from a ``CampaignProposal`` in a
single transactional flow:

  1. create_campaign  — CampaignBudget + Campaign (PAUSED)
  2. create_ad_groups — AdGroup objects, one per AdGroupProposal
  3. create_keywords  — AdGroupCriterion (keyword) per ad group
  4. create_ads       — AdGroupAd (RSA) per ad group
  5. create_negative_keywords — CampaignCriterion (negative) at campaign level

If any step raises, ``delete_draft_campaign`` removes every resource
created so far so no orphan resources are left in the customer account.

``enable_campaign`` is a separate, explicit call — only triggered after a
second explicit user confirmation.

Every successful mutation writes an AuditLog entry with the full payload.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from adcopilot.application.ports.audit_log_repository import AuditLogRepository
from adcopilot.application.ports.campaign_writer import CreatedCampaignResources
from adcopilot.config import Settings
from adcopilot.domain.audit_log import AuditLog, AuditLogId
from adcopilot.domain.entities import AccountId
from adcopilot.domain.exceptions import GoogleAdsAuthError, GoogleAdsUnavailable
from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CampaignProposal,
    KeywordProposal,
    MatchType,
)
from adcopilot.domain.recommendation import RecommendationId
from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter, is_google_auth_error

logger = structlog.get_logger(__name__)

# Sentinel recommendation_id used for campaign-write audit entries
# (campaign creation is not recommendation-driven).
_CAMPAIGN_WRITE_REC_ID = RecommendationId("00000000-0000-0000-0000-000000000000")

_MATCH_TYPE_MAP: dict[str, str] = {
    MatchType.BROAD: "BROAD",
    MatchType.PHRASE: "PHRASE",
    MatchType.EXACT: "EXACT",
}


def _wrap_exc(operation: str, exc: Exception) -> Exception:
    if is_google_auth_error(exc):
        return GoogleAdsAuthError(str(exc))
    return GoogleAdsUnavailable(f"{operation} failed: {exc}")


class CampaignWriter:
    """Implements ``CampaignWriterPort`` against the real Google Ads API v24+."""

    def __init__(
        self,
        settings: Settings,
        audit_log_repo: AuditLogRepository,
        account_id: AccountId,
    ) -> None:
        self._settings = settings
        self._audit = audit_log_repo
        self._account_id = account_id
        self._client_adapter = GoogleAdsClientAdapter(settings)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_client(self, refresh_token: str) -> Any:
        return self._client_adapter._build_client(refresh_token)

    def _cid(self, customer_id: str) -> str:
        return customer_id.replace("-", "")

    async def _log(self, kind: str, payload: dict[str, Any]) -> None:
        log = AuditLog(
            id=AuditLogId(str(uuid.uuid4())),
            recommendation_id=_CAMPAIGN_WRITE_REC_ID,
            account_id=self._account_id,
            kind=kind,
            action="EXECUTE",
            payload=payload,
            created_at=datetime.now(UTC),
        )
        await self._audit.save(log)

    # ------------------------------------------------------------------
    # Step 1 — Campaign + Budget
    # ------------------------------------------------------------------

    async def create_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        proposal: CampaignProposal,
    ) -> tuple[str, str]:
        """Create a campaign budget and PAUSED campaign; return (campaign_rn, budget_rn)."""
        try:
            client = self._build_client(refresh_token)
            cid = self._cid(customer_id)

            # --- Budget ---
            budget_service = client.get_service("CampaignBudgetService")
            budget_op = client.get_type("CampaignBudgetOperation")
            budget = budget_op.create
            budget.name = f"{proposal.campaign_name} Budget"
            budget.amount_micros = proposal.daily_budget_micros
            budget.delivery_method = (
                client.enums.BudgetDeliveryMethodEnum.STANDARD
            )

            budget_response = budget_service.mutate_campaign_budgets(
                customer_id=cid, operations=[budget_op]
            )
            budget_rn: str = budget_response.results[0].resource_name

            # --- Campaign ---
            campaign_service = client.get_service("CampaignService")
            campaign_op = client.get_type("CampaignOperation")
            campaign = campaign_op.create
            campaign.name = proposal.campaign_name
            campaign.status = client.enums.CampaignStatusEnum.PAUSED
            campaign.campaign_budget = budget_rn
            campaign.advertising_channel_type = (
                client.enums.AdvertisingChannelTypeEnum.SEARCH
            )

            strategy = proposal.bidding_strategy.upper().replace(" ", "_")
            _STRATEGY_MAP = {
                "MAXIMIZE_CONVERSIONS": "maximize_conversions",
                "MAXIMIZE_CONVERSION_VALUE": "maximize_conversion_value",
                "MAXIMIZE_CLICKS": "target_spend",
                "TARGET_CPA": "target_cpa",
                "TARGET_ROAS": "target_roas",
            }
            field = _STRATEGY_MAP.get(strategy, "maximize_conversions")
            sub = getattr(campaign, field)
            sub.CopyFrom(type(sub)())

            # Geographic targeting
            geo_target = campaign.geo_target_type_setting
            geo_target.positive_geo_target_type = (
                client.enums.PositiveGeoTargetTypeEnum.PRESENCE_OR_INTEREST
            )

            campaign_response = campaign_service.mutate_campaigns(
                customer_id=cid, operations=[campaign_op]
            )
            campaign_rn: str = campaign_response.results[0].resource_name

            logger.info(
                "campaign_created",
                customer_id=customer_id,
                campaign_rn=campaign_rn,
                budget_rn=budget_rn,
            )
            await self._log(
                "CAMPAIGN_CREATE",
                {
                    "campaign_resource_name": campaign_rn,
                    "budget_resource_name": budget_rn,
                    "campaign_name": proposal.campaign_name,
                    "daily_budget_micros": proposal.daily_budget_micros,
                    "bidding_strategy": proposal.bidding_strategy,
                    "proposal_id": proposal.id,
                },
            )
            return campaign_rn, budget_rn

        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_exc("create_campaign", exc) from exc

    # ------------------------------------------------------------------
    # Step 2 — Ad Groups
    # ------------------------------------------------------------------

    async def create_ad_groups(
        self,
        customer_id: str,
        refresh_token: str,
        campaign_resource_name: str,
        ad_group_proposals: list[AdGroupProposal],
    ) -> list[str]:
        """Create ad groups; return list of resource_names in proposal order."""
        try:
            client = self._build_client(refresh_token)
            cid = self._cid(customer_id)
            ag_service = client.get_service("AdGroupService")

            operations = []
            for agp in ad_group_proposals:
                op = client.get_type("AdGroupOperation")
                ag = op.create
                ag.name = agp.name
                ag.campaign = campaign_resource_name
                ag.status = client.enums.AdGroupStatusEnum.ENABLED
                ag.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
                operations.append(op)

            response = ag_service.mutate_ad_groups(
                customer_id=cid, operations=operations
            )
            rns = [r.resource_name for r in response.results]

            logger.info(
                "ad_groups_created",
                customer_id=customer_id,
                count=len(rns),
                campaign_rn=campaign_resource_name,
            )
            await self._log(
                "AD_GROUPS_CREATE",
                {
                    "campaign_resource_name": campaign_resource_name,
                    "ad_group_resource_names": rns,
                    "names": [ag.name for ag in ad_group_proposals],
                },
            )
            return rns

        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_exc("create_ad_groups", exc) from exc

    # ------------------------------------------------------------------
    # Step 3 — Keywords
    # ------------------------------------------------------------------

    async def create_keywords(
        self,
        customer_id: str,
        refresh_token: str,
        ad_group_resource_name: str,
        keyword_proposals: list[KeywordProposal],
    ) -> list[str]:
        """Create keywords under *ad_group_resource_name*; return resource_names."""
        try:
            client = self._build_client(refresh_token)
            cid = self._cid(customer_id)
            criterion_service = client.get_service("AdGroupCriterionService")

            operations = []
            for kp in keyword_proposals:
                op = client.get_type("AdGroupCriterionOperation")
                criterion = op.create
                criterion.ad_group = ad_group_resource_name
                criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
                criterion.keyword.text = kp.text
                match_str = _MATCH_TYPE_MAP.get(kp.match_type, "PHRASE")
                criterion.keyword.match_type = getattr(
                    client.enums.KeywordMatchTypeEnum,
                    match_str,
                    client.enums.KeywordMatchTypeEnum.PHRASE,
                )
                operations.append(op)

            response = criterion_service.mutate_ad_group_criteria(
                customer_id=cid, operations=operations
            )
            rns = [r.resource_name for r in response.results]

            logger.info(
                "keywords_created",
                customer_id=customer_id,
                ad_group_rn=ad_group_resource_name,
                count=len(rns),
            )
            await self._log(
                "KEYWORDS_CREATE",
                {
                    "ad_group_resource_name": ad_group_resource_name,
                    "keyword_resource_names": rns,
                    "keywords": [
                        {"text": k.text, "match_type": k.match_type}
                        for k in keyword_proposals
                    ],
                },
            )
            return rns

        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_exc("create_keywords", exc) from exc

    # ------------------------------------------------------------------
    # Step 4 — Ads (RSA)
    # ------------------------------------------------------------------

    async def create_ads(
        self,
        customer_id: str,
        refresh_token: str,
        ad_group_resource_name: str,
        ad_proposals: list[AdProposal],
    ) -> list[str]:
        """Create RSA ads under *ad_group_resource_name*; return resource_names."""
        try:
            client = self._build_client(refresh_token)
            cid = self._cid(customer_id)
            ad_group_ad_service = client.get_service("AdGroupAdService")

            operations = []
            for adp in ad_proposals:
                op = client.get_type("AdGroupAdOperation")
                ad_group_ad = op.create
                ad_group_ad.ad_group = ad_group_resource_name
                ad_group_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED

                ad = ad_group_ad.ad
                ad.final_urls.append(adp.final_url)

                rsa = ad.responsive_search_ad
                for i, hl in enumerate(adp.headlines[:15]):
                    asset = client.get_type("AdTextAsset")
                    asset.text = hl
                    # Pin first 3 headlines to positions 1-3
                    if i < 3:
                        asset.pinned_field = getattr(
                            client.enums.ServedAssetFieldTypeEnum,
                            f"HEADLINE_{i + 1}",
                            client.enums.ServedAssetFieldTypeEnum.UNSPECIFIED,
                        )
                    rsa.headlines.append(asset)

                for i, desc in enumerate(adp.descriptions[:4]):
                    asset = client.get_type("AdTextAsset")
                    asset.text = desc
                    rsa.descriptions.append(asset)

                if adp.path_segments[0]:
                    rsa.path1 = adp.path_segments[0]
                if adp.path_segments[1]:
                    rsa.path2 = adp.path_segments[1]

                operations.append(op)

            response = ad_group_ad_service.mutate_ad_group_ads(
                customer_id=cid, operations=operations
            )
            rns = [r.resource_name for r in response.results]

            logger.info(
                "ads_created",
                customer_id=customer_id,
                ad_group_rn=ad_group_resource_name,
                count=len(rns),
            )
            await self._log(
                "ADS_CREATE",
                {
                    "ad_group_resource_name": ad_group_resource_name,
                    "ad_resource_names": rns,
                    "ads": [
                        {
                            "headlines": adp.headlines,
                            "descriptions": adp.descriptions,
                            "final_url": adp.final_url,
                        }
                        for adp in ad_proposals
                    ],
                },
            )
            return rns

        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_exc("create_ads", exc) from exc

    # ------------------------------------------------------------------
    # Step 5 — Campaign-level negative keywords
    # ------------------------------------------------------------------

    async def create_negative_keywords(
        self,
        customer_id: str,
        refresh_token: str,
        campaign_resource_name: str,
        negatives: list[str],
    ) -> list[str]:
        """Create campaign-level negative keywords; return resource_names."""
        if not negatives:
            return []
        try:
            client = self._build_client(refresh_token)
            cid = self._cid(customer_id)
            criterion_service = client.get_service("CampaignCriterionService")

            operations = []
            for text in negatives:
                op = client.get_type("CampaignCriterionOperation")
                criterion = op.create
                criterion.campaign = campaign_resource_name
                criterion.negative = True
                criterion.keyword.text = text
                criterion.keyword.match_type = (
                    client.enums.KeywordMatchTypeEnum.BROAD
                )
                operations.append(op)

            response = criterion_service.mutate_campaign_criteria(
                customer_id=cid, operations=operations
            )
            rns = [r.resource_name for r in response.results]

            logger.info(
                "negative_keywords_created",
                customer_id=customer_id,
                campaign_rn=campaign_resource_name,
                count=len(rns),
            )
            await self._log(
                "NEGATIVE_KEYWORDS_CREATE",
                {
                    "campaign_resource_name": campaign_resource_name,
                    "negative_resource_names": rns,
                    "keywords": negatives,
                },
            )
            return rns

        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_exc("create_negative_keywords", exc) from exc

    # ------------------------------------------------------------------
    # Enable (second confirmation)
    # ------------------------------------------------------------------

    async def enable_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        campaign_resource_name: str,
    ) -> None:
        """Transition campaign from PAUSED → ENABLED.

        Only called after explicit second user confirmation.
        """
        try:
            client = self._build_client(refresh_token)
            cid = self._cid(customer_id)
            campaign_service = client.get_service("CampaignService")

            op = client.get_type("CampaignOperation")
            campaign = op.update
            campaign.resource_name = campaign_resource_name
            campaign.status = client.enums.CampaignStatusEnum.ENABLED
            from google.protobuf import field_mask_pb2
            op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
            campaign_service.mutate_campaigns(customer_id=cid, operations=[op])

            logger.info(
                "campaign_enabled",
                customer_id=customer_id,
                campaign_rn=campaign_resource_name,
            )
            await self._log(
                "CAMPAIGN_ENABLE",
                {"campaign_resource_name": campaign_resource_name},
            )

        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_exc("enable_campaign", exc) from exc

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    async def delete_draft_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        resources: CreatedCampaignResources,
    ) -> None:
        """Delete all resources created so far; safe to call partially populated.

        Deletion order (reverse creation): ads → keywords → ad groups →
        negatives → campaign → budget.

        Every deletion is attempted; errors are logged but do not abort the
        rollback of remaining resources.
        """
        try:
            client = self._build_client(refresh_token)
            cid = self._cid(customer_id)

            errors: list[str] = []

            # Ads
            if resources.ad_resource_names:
                try:
                    aga_service = client.get_service("AdGroupAdService")
                    ops = []
                    for rn in resources.ad_resource_names:
                        op = client.get_type("AdGroupAdOperation")
                        op.remove = rn
                        ops.append(op)
                    aga_service.mutate_ad_group_ads(customer_id=cid, operations=ops)
                except Exception as exc:
                    errors.append(f"ads: {exc}")

            # Keywords
            if resources.keyword_resource_names:
                try:
                    agc_service = client.get_service("AdGroupCriterionService")
                    ops = []
                    for rn in resources.keyword_resource_names:
                        op = client.get_type("AdGroupCriterionOperation")
                        op.remove = rn
                        ops.append(op)
                    agc_service.mutate_ad_group_criteria(customer_id=cid, operations=ops)
                except Exception as exc:
                    errors.append(f"keywords: {exc}")

            # Ad groups
            if resources.ad_group_resource_names:
                try:
                    ag_service = client.get_service("AdGroupService")
                    ops = []
                    for rn in resources.ad_group_resource_names:
                        op = client.get_type("AdGroupOperation")
                        op.remove = rn
                        ops.append(op)
                    ag_service.mutate_ad_groups(customer_id=cid, operations=ops)
                except Exception as exc:
                    errors.append(f"ad_groups: {exc}")

            # Negative keywords
            if resources.negative_resource_names:
                try:
                    cc_service = client.get_service("CampaignCriterionService")
                    ops = []
                    for rn in resources.negative_resource_names:
                        op = client.get_type("CampaignCriterionOperation")
                        op.remove = rn
                        ops.append(op)
                    cc_service.mutate_campaign_criteria(customer_id=cid, operations=ops)
                except Exception as exc:
                    errors.append(f"negatives: {exc}")

            # Campaign
            if resources.campaign_resource_name:
                try:
                    campaign_service = client.get_service("CampaignService")
                    op = client.get_type("CampaignOperation")
                    op.remove = resources.campaign_resource_name
                    campaign_service.mutate_campaigns(customer_id=cid, operations=[op])
                except Exception as exc:
                    errors.append(f"campaign: {exc}")

            # Budget (last — campaign must be removed first)
            if resources.budget_resource_name:
                try:
                    budget_service = client.get_service("CampaignBudgetService")
                    op = client.get_type("CampaignBudgetOperation")
                    op.remove = resources.budget_resource_name
                    budget_service.mutate_campaign_budgets(customer_id=cid, operations=[op])
                except Exception as exc:
                    errors.append(f"budget: {exc}")

            if errors:
                logger.error(
                    "rollback_partial_failure",
                    customer_id=customer_id,
                    errors=errors,
                )
            else:
                logger.info(
                    "rollback_complete",
                    customer_id=customer_id,
                    campaign_rn=resources.campaign_resource_name,
                )

            await self._log(
                "CAMPAIGN_ROLLBACK",
                {
                    "campaign_resource_name": resources.campaign_resource_name,
                    "budget_resource_name": resources.budget_resource_name,
                    "ad_group_resource_names": resources.ad_group_resource_names,
                    "rollback_errors": errors,
                },
            )

        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_exc("delete_draft_campaign", exc) from exc
