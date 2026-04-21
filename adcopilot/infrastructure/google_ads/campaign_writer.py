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
from adcopilot.domain.launch.audience_signals import AudienceSignal
from adcopilot.domain.launch.schedule_rules import AdScheduleEntry
from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CalloutProposal,
    CampaignProposal,
    KeywordProposal,
    MatchType,
    SitelinkProposal,
    StructuredSnippetProposal,
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

                for i, desc in enumerate(adp.descriptions[:4]):  # noqa: B007
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

    async def create_extensions(
        self,
        customer_id: str,
        refresh_token: str,
        campaign_resource_name: str,
        sitelinks: list[SitelinkProposal],
        callouts: list[CalloutProposal],
        snippets: list[StructuredSnippetProposal],
    ) -> list[str]:
        """Create campaign-level sitelink, callout, and structured snippet assets.

        Uses AssetService to create assets then CampaignAssetService to link them.
        Returns a list of CampaignAsset resource names for rollback tracking.
        """
        if not sitelinks and not callouts and not snippets:
            return []
        try:
            client = self._build_client(refresh_token)
            cid = self._cid(customer_id)
            asset_service = client.get_service("AssetService")
            campaign_asset_service = client.get_service("CampaignAssetService")

            asset_ops: list[Any] = []

            # --- Sitelinks ---
            for sl in sitelinks:
                op = client.get_type("AssetOperation")
                asset = op.create
                asset.sitelink_asset.link_text = sl.link_text
                asset.sitelink_asset.description1 = sl.description1
                asset.sitelink_asset.description2 = sl.description2
                asset.final_urls.append(sl.final_url)
                asset_ops.append(op)

            # --- Callouts ---
            for co in callouts:
                op = client.get_type("AssetOperation")
                asset = op.create
                asset.callout_asset.callout_text = co.text
                asset_ops.append(op)

            # --- Structured snippets ---
            for sn in snippets:
                op = client.get_type("AssetOperation")
                asset = op.create
                asset.structured_snippet_asset.header = sn.header
                for v in sn.values:
                    asset.structured_snippet_asset.values.append(v)
                asset_ops.append(op)

            asset_response = asset_service.mutate_assets(
                customer_id=cid, operations=asset_ops
            )
            asset_rns = [r.resource_name for r in asset_response.results]

            # Determine field types for linking
            n_sitelinks = len(sitelinks)
            n_callouts = len(callouts)
            n_snippets = len(snippets)
            field_types: list[Any] = (
                [client.enums.AssetFieldTypeEnum.SITELINK] * n_sitelinks
                + [client.enums.AssetFieldTypeEnum.CALLOUT] * n_callouts
                + [client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET] * n_snippets
            )

            # Link assets to campaign
            ca_ops: list[Any] = []
            for asset_rn, field_type in zip(asset_rns, field_types):
                op = client.get_type("CampaignAssetOperation")
                ca = op.create
                ca.campaign = campaign_resource_name
                ca.asset = asset_rn
                ca.field_type = field_type
                ca_ops.append(op)

            ca_response = campaign_asset_service.mutate_campaign_assets(
                customer_id=cid, operations=ca_ops
            )
            ca_rns = [r.resource_name for r in ca_response.results]

            logger.info(
                "extensions_created",
                customer_id=customer_id,
                campaign_rn=campaign_resource_name,
                sitelinks=n_sitelinks,
                callouts=n_callouts,
                snippets=n_snippets,
            )
            await self._log(
                "EXTENSIONS_CREATE",
                {
                    "campaign_resource_name": campaign_resource_name,
                    "asset_resource_names": asset_rns,
                    "campaign_asset_resource_names": ca_rns,
                },
            )
            return ca_rns

        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_exc("create_extensions", exc) from exc

    # ------------------------------------------------------------------
    # Step 1.5 — Ad schedule (dayparting)
    # ------------------------------------------------------------------

    async def create_ad_schedule(
        self,
        customer_id: str,
        refresh_token: str,
        campaign_resource_name: str,
        schedule: list[AdScheduleEntry],
    ) -> list[str]:
        """Create CampaignCriterion ad schedule entries; return resource names."""
        if not schedule:
            return []
        try:
            client = self._build_client(refresh_token)
            cid = self._cid(customer_id)
            cc_service = client.get_service("CampaignCriterionService")

            _DAY_MAP = {
                "MONDAY": client.enums.DayOfWeekEnum.MONDAY,
                "TUESDAY": client.enums.DayOfWeekEnum.TUESDAY,
                "WEDNESDAY": client.enums.DayOfWeekEnum.WEDNESDAY,
                "THURSDAY": client.enums.DayOfWeekEnum.THURSDAY,
                "FRIDAY": client.enums.DayOfWeekEnum.FRIDAY,
                "SATURDAY": client.enums.DayOfWeekEnum.SATURDAY,
                "SUNDAY": client.enums.DayOfWeekEnum.SUNDAY,
            }
            _MINUTE_MAP = {0: 0, 15: 15, 30: 30, 45: 45}

            ops: list[Any] = []
            for entry in schedule:
                op = client.get_type("CampaignCriterionOperation")
                criterion = op.create
                criterion.campaign = campaign_resource_name
                criterion.negative = False
                sched = criterion.ad_schedule
                sched.day_of_week = _DAY_MAP[entry.day_of_week]
                sched.start_hour = entry.start_hour
                sched.start_minute = _MINUTE_MAP.get(entry.start_minute, 0)
                sched.end_hour = entry.end_hour
                sched.end_minute = _MINUTE_MAP.get(entry.end_minute, 0)
                ops.append(op)

            response = cc_service.mutate_campaign_criteria(
                customer_id=cid, operations=ops
            )
            resource_names = [r.resource_name for r in response.results]

            logger.info(
                "ad_schedule_created",
                customer_id=customer_id,
                campaign_rn=campaign_resource_name,
                entries=len(schedule),
            )
            await self._log(
                "AD_SCHEDULE_CREATE",
                {
                    "campaign_resource_name": campaign_resource_name,
                    "schedule_entries": len(schedule),
                    "criterion_resource_names": resource_names,
                },
            )
            return resource_names

        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_exc("create_ad_schedule", exc) from exc

    # ------------------------------------------------------------------
    # Step 1b — Brand Search campaign (MID/GROWTH only)
    # ------------------------------------------------------------------

    async def create_brand_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        proposal: "CampaignProposal",
    ) -> tuple[str, str]:
        """Create a separate Brand Search campaign (MAXIMIZE_CLICKS, exact-match brand keywords).

        Returns (campaign_resource_name, budget_resource_name).
        """
        if not proposal.brand_campaign_name or not proposal.brand_keywords:
            return "", ""
        try:
            client = self._build_client(refresh_token)
            cid = self._cid(customer_id)

            # Budget
            budget_service = client.get_service("CampaignBudgetService")
            budget_op = client.get_type("CampaignBudgetOperation")
            budget = budget_op.create
            budget.name = f"{proposal.brand_campaign_name} Budget"
            budget.amount_micros = proposal.brand_daily_budget_micros
            budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
            budget_response = budget_service.mutate_campaign_budgets(
                customer_id=cid, operations=[budget_op]
            )
            budget_rn: str = budget_response.results[0].resource_name

            # Campaign (always MAXIMIZE_CLICKS — brand traffic is cheap and high-intent)
            campaign_service = client.get_service("CampaignService")
            campaign_op = client.get_type("CampaignOperation")
            campaign = campaign_op.create
            campaign.name = proposal.brand_campaign_name
            campaign.status = client.enums.CampaignStatusEnum.PAUSED
            campaign.campaign_budget = budget_rn
            campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
            campaign.target_spend.CopyFrom(type(campaign.target_spend)())
            campaign_response = campaign_service.mutate_campaigns(
                customer_id=cid, operations=[campaign_op]
            )
            campaign_rn: str = campaign_response.results[0].resource_name

            # Ad group
            ag_service = client.get_service("AdGroupService")
            ag_op = client.get_type("AdGroupOperation")
            ag = ag_op.create
            ag.name = "Brand Keywords"
            ag.campaign = campaign_rn
            ag.status = client.enums.AdGroupStatusEnum.ENABLED
            ag_response = ag_service.mutate_ad_groups(customer_id=cid, operations=[ag_op])
            ag_rn: str = ag_response.results[0].resource_name

            # Keywords (exact match)
            agc_service = client.get_service("AdGroupCriterionService")
            kw_ops: list[Any] = []
            for kw in proposal.brand_keywords:
                op = client.get_type("AdGroupCriterionOperation")
                criterion = op.create
                criterion.ad_group = ag_rn
                criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
                criterion.keyword.text = kw.text
                criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.EXACT
                kw_ops.append(op)
            agc_service.mutate_ad_group_criteria(customer_id=cid, operations=kw_ops)

            # Brand ad (if present)
            if proposal.brand_ad:
                ad_service = client.get_service("AdGroupAdService")
                ad_op = client.get_type("AdGroupAdOperation")
                ad = ad_op.create
                ad.ad_group = ag_rn
                ad.status = client.enums.AdGroupAdStatusEnum.ENABLED
                rsa = ad.ad.responsive_search_ad
                for h in proposal.brand_ad.headlines[:15]:
                    asset = client.get_type("AdTextAsset")
                    asset.text = h[:30]
                    rsa.headlines.append(asset)
                for d in proposal.brand_ad.descriptions[:4]:
                    asset = client.get_type("AdTextAsset")
                    asset.text = d[:90]
                    rsa.descriptions.append(asset)
                ad.ad.final_urls.append(proposal.brand_ad.final_url)
                ad_service.mutate_ad_group_ads(customer_id=cid, operations=[ad_op])

            logger.info(
                "brand_campaign_created",
                customer_id=customer_id,
                campaign_rn=campaign_rn,
            )
            await self._log(
                "BRAND_CAMPAIGN_CREATE",
                {
                    "campaign_resource_name": campaign_rn,
                    "budget_resource_name": budget_rn,
                    "brand_campaign_name": proposal.brand_campaign_name,
                },
            )
            return campaign_rn, budget_rn

        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_exc("create_brand_campaign", exc) from exc

    # ------------------------------------------------------------------
    # Step 2.5 — Observation-mode audience signals
    # ------------------------------------------------------------------

    async def create_audience_signals(
        self,
        customer_id: str,
        refresh_token: str,
        ad_group_resource_names: list[str],
        audience_signals: list[AudienceSignal],
    ) -> list[str]:
        """Add in-market/affinity audiences in OBSERVATION mode to ad groups.

        Observation mode does not restrict reach — it layers audience data so
        Smart Bidding can learn which segments convert best.
        Returns AdGroupCriterion resource names for rollback.
        """
        if not ad_group_resource_names or not audience_signals:
            return []
        try:
            client = self._build_client(refresh_token)
            cid = self._cid(customer_id)
            agc_service = client.get_service("AdGroupCriterionService")

            ops: list[Any] = []
            for ag_rn in ad_group_resource_names:
                for signal in audience_signals:
                    op = client.get_type("AdGroupCriterionOperation")
                    criterion = op.create
                    criterion.ad_group = ag_rn
                    criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
                    # Observation mode — does not restrict targeting
                    criterion.negative = False
                    criterion.bid_modifier = 1.0
                    criterion.user_interest.user_interest_category = (
                        f"userinterests/{signal.segment_id}"
                    )
                    ops.append(op)

            response = agc_service.mutate_ad_group_criteria(
                customer_id=cid, operations=ops
            )
            resource_names = [r.resource_name for r in response.results]

            logger.info(
                "audience_signals_created",
                customer_id=customer_id,
                ad_groups=len(ad_group_resource_names),
                signals=len(audience_signals),
            )
            await self._log(
                "AUDIENCE_SIGNALS_CREATE",
                {
                    "ad_group_resource_names": ad_group_resource_names,
                    "audience_segment_ids": [s.segment_id for s in audience_signals],
                    "criterion_resource_names": resource_names,
                },
            )
            return resource_names

        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_exc("create_audience_signals", exc) from exc

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

            # Audience criteria (AdGroupCriterion)
            if resources.audience_resource_names:
                try:
                    agc_service = client.get_service("AdGroupCriterionService")
                    ops = []
                    for rn in resources.audience_resource_names:
                        op = client.get_type("AdGroupCriterionOperation")
                        op.remove = rn
                        ops.append(op)
                    agc_service.mutate_ad_group_criteria(customer_id=cid, operations=ops)
                except Exception as exc:
                    errors.append(f"audiences: {exc}")

            # Extension assets (CampaignAsset links)
            if resources.extension_resource_names:
                try:
                    ca_service = client.get_service("CampaignAssetService")
                    ops = []
                    for rn in resources.extension_resource_names:
                        op = client.get_type("CampaignAssetOperation")
                        op.remove = rn
                        ops.append(op)
                    ca_service.mutate_campaign_assets(customer_id=cid, operations=ops)
                except Exception as exc:
                    errors.append(f"extensions: {exc}")

            # Ad schedule criteria (CampaignCriterion)
            if resources.schedule_resource_names:
                try:
                    cc_service = client.get_service("CampaignCriterionService")
                    ops = []
                    for rn in resources.schedule_resource_names:
                        op = client.get_type("CampaignCriterionOperation")
                        op.remove = rn
                        ops.append(op)
                    cc_service.mutate_campaign_criteria(customer_id=cid, operations=ops)
                except Exception as exc:
                    errors.append(f"schedule: {exc}")

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

            # Brand campaign + budget
            if resources.brand_campaign_resource_name:
                try:
                    campaign_service = client.get_service("CampaignService")
                    op = client.get_type("CampaignOperation")
                    op.remove = resources.brand_campaign_resource_name
                    campaign_service.mutate_campaigns(customer_id=cid, operations=[op])
                except Exception as exc:
                    errors.append(f"brand_campaign: {exc}")
            if resources.brand_budget_resource_name:
                try:
                    budget_service = client.get_service("CampaignBudgetService")
                    op = client.get_type("CampaignBudgetOperation")
                    op.remove = resources.brand_budget_resource_name
                    budget_service.mutate_campaign_budgets(customer_id=cid, operations=[op])
                except Exception as exc:
                    errors.append(f"brand_budget: {exc}")

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
