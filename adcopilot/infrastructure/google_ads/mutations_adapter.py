"""Google Ads mutations adapter — wraps the google-ads library for write operations."""

from __future__ import annotations

from typing import Any

import structlog

from adcopilot.config import Settings
from adcopilot.domain.exceptions import GoogleAdsAuthError, GoogleAdsUnavailable
from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter, is_google_auth_error

logger = structlog.get_logger(__name__)


def _wrap_mutation_exc(operation: str, exc: Exception) -> Exception:
    """Map a raw Google Ads exception to the appropriate domain exception."""
    if is_google_auth_error(exc):
        return GoogleAdsAuthError(str(exc))
    return GoogleAdsUnavailable(f"{operation} failed: {exc}")


class GoogleAdsMutationsAdapter:
    """Implements GoogleAdsMutationsPort against the real Google Ads API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = GoogleAdsClientAdapter(settings)

    def _build_client(self, refresh_token: str) -> Any:
        return self._client._build_client(refresh_token)

    async def pause_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        criterion_id: int,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            ad_group_criterion_service = client.get_service("AdGroupCriterionService")
            resource_name = client.get_service("AdGroupCriterionService").ad_group_criterion_path(
                customer_id.replace("-", ""), ad_group_id, criterion_id
            )
            criterion_operation = client.get_type("AdGroupCriterionOperation")
            criterion = criterion_operation.update
            criterion.resource_name = resource_name
            criterion.status = client.enums.AdGroupCriterionStatusEnum.PAUSED
            from google.protobuf import field_mask_pb2
            criterion_operation.update_mask.CopyFrom(
                field_mask_pb2.FieldMask(paths=["status"])
            )
            ad_group_criterion_service.mutate_ad_group_criteria(
                customer_id=customer_id.replace("-", ""),
                operations=[criterion_operation],
            )
            logger.info("keyword paused", customer_id=customer_id, criterion_id=criterion_id)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("pause_keyword", exc) from exc

    async def pause_ad(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        ad_id: int,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            ad_group_ad_service = client.get_service("AdGroupAdService")
            resource_name = ad_group_ad_service.ad_group_ad_path(
                customer_id.replace("-", ""), ad_group_id, ad_id
            )
            operation = client.get_type("AdGroupAdOperation")
            ad = operation.update
            ad.resource_name = resource_name
            ad.status = client.enums.AdGroupAdStatusEnum.PAUSED
            from google.protobuf import field_mask_pb2
            operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
            ad_group_ad_service.mutate_ad_group_ads(
                customer_id=customer_id.replace("-", ""),
                operations=[operation],
            )
            logger.info("ad paused", customer_id=customer_id, ad_id=ad_id)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("pause_ad", exc) from exc

    async def add_ad_group_negative_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            ad_group_criterion_service = client.get_service("AdGroupCriterionService")
            operation = client.get_type("AdGroupCriterionOperation")
            criterion = operation.create
            criterion.ad_group = client.get_service("AdGroupService").ad_group_path(
                customer_id.replace("-", ""), ad_group_id
            )
            criterion.negative = True
            criterion.keyword.text = keyword_text
            criterion.keyword.match_type = getattr(
                client.enums.KeywordMatchTypeEnum, match_type, client.enums.KeywordMatchTypeEnum.EXACT
            )
            ad_group_criterion_service.mutate_ad_group_criteria(
                customer_id=customer_id.replace("-", ""),
                operations=[operation],
            )
            logger.info("negative keyword added", customer_id=customer_id, keyword=keyword_text)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("add_ad_group_negative_keyword", exc) from exc

    async def update_campaign_budget(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        new_budget_micros: int,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            # Look up budget_id from the campaign
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT campaign_budget.id, campaign_budget.resource_name
                FROM campaign
                WHERE campaign.id = {campaign_id}
                LIMIT 1
            """
            response = ga_service.search(customer_id=customer_id.replace("-", ""), query=query)
            budget_resource_name = None
            for row in response:
                budget_resource_name = row.campaign_budget.resource_name
                break
            if budget_resource_name is None:
                raise GoogleAdsUnavailable(f"Campaign {campaign_id} budget not found")

            campaign_budget_service = client.get_service("CampaignBudgetService")
            operation = client.get_type("CampaignBudgetOperation")
            budget = operation.update
            budget.resource_name = budget_resource_name
            budget.amount_micros = new_budget_micros
            from google.protobuf import field_mask_pb2
            operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["amount_micros"]))
            campaign_budget_service.mutate_campaign_budgets(
                customer_id=customer_id.replace("-", ""),
                operations=[operation],
            )
            logger.info(
                "campaign budget updated",
                customer_id=customer_id,
                campaign_id=campaign_id,
                new_budget_micros=new_budget_micros,
            )
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("update_campaign_budget", exc) from exc

    async def enable_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        criterion_id: int,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            ad_group_criterion_service = client.get_service("AdGroupCriterionService")
            resource_name = ad_group_criterion_service.ad_group_criterion_path(
                customer_id.replace("-", ""), ad_group_id, criterion_id
            )
            operation = client.get_type("AdGroupCriterionOperation")
            criterion = operation.update
            criterion.resource_name = resource_name
            criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
            from google.protobuf import field_mask_pb2
            operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
            ad_group_criterion_service.mutate_ad_group_criteria(
                customer_id=customer_id.replace("-", ""),
                operations=[operation],
            )
            logger.info("keyword enabled", customer_id=customer_id, criterion_id=criterion_id)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("enable_keyword", exc) from exc

    async def enable_ad(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        ad_id: int,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            ad_group_ad_service = client.get_service("AdGroupAdService")
            resource_name = ad_group_ad_service.ad_group_ad_path(
                customer_id.replace("-", ""), ad_group_id, ad_id
            )
            operation = client.get_type("AdGroupAdOperation")
            ad = operation.update
            ad.resource_name = resource_name
            ad.status = client.enums.AdGroupAdStatusEnum.ENABLED
            from google.protobuf import field_mask_pb2
            operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
            ad_group_ad_service.mutate_ad_group_ads(
                customer_id=customer_id.replace("-", ""),
                operations=[operation],
            )
            logger.info("ad enabled", customer_id=customer_id, ad_id=ad_id)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("enable_ad", exc) from exc

    async def remove_ad_group_negative_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT ad_group_criterion.resource_name
                FROM ad_group_criterion
                WHERE ad_group_criterion.ad_group ~ '{ad_group_id}'
                  AND ad_group_criterion.negative = TRUE
                  AND ad_group_criterion.keyword.text = '{keyword_text}'
                  AND ad_group_criterion.keyword.match_type = '{match_type}'
                LIMIT 1
            """
            response = ga_service.search(customer_id=customer_id.replace("-", ""), query=query)
            resource_name = None
            for row in response:
                resource_name = row.ad_group_criterion.resource_name
                break
            if resource_name is None:
                logger.warning(
                    "negative keyword not found for removal",
                    customer_id=customer_id,
                    keyword=keyword_text,
                )
                return
            ad_group_criterion_service = client.get_service("AdGroupCriterionService")
            operation = client.get_type("AdGroupCriterionOperation")
            operation.remove = resource_name
            ad_group_criterion_service.mutate_ad_group_criteria(
                customer_id=customer_id.replace("-", ""),
                operations=[operation],
            )
            logger.info(
                "negative keyword removed", customer_id=customer_id, keyword=keyword_text
            )
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("remove_ad_group_negative_keyword", exc) from exc

    async def change_keyword_match_type(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        criterion_id: int,
        match_type: str,
    ) -> None:
        """Update a keyword's match type (e.g. BROAD → PHRASE or EXACT)."""
        try:
            client = self._build_client(refresh_token)
            ad_group_criterion_service = client.get_service("AdGroupCriterionService")
            resource_name = ad_group_criterion_service.ad_group_criterion_path(
                customer_id.replace("-", ""), ad_group_id, criterion_id
            )
            operation = client.get_type("AdGroupCriterionOperation")
            criterion = operation.update
            criterion.resource_name = resource_name
            criterion.keyword.match_type = getattr(
                client.enums.KeywordMatchTypeEnum,
                match_type,
                client.enums.KeywordMatchTypeEnum.PHRASE,
            )
            from google.protobuf import field_mask_pb2
            operation.update_mask.CopyFrom(
                field_mask_pb2.FieldMask(paths=["keyword.match_type"])
            )
            ad_group_criterion_service.mutate_ad_group_criteria(
                customer_id=customer_id.replace("-", ""),
                operations=[operation],
            )
            logger.info(
                "keyword match type changed",
                customer_id=customer_id,
                criterion_id=criterion_id,
                match_type=match_type,
            )
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("change_keyword_match_type", exc) from exc

    async def set_campaign_bidding_strategy(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        bidding_strategy: str,
    ) -> None:
        """Switch a campaign to a different bidding strategy.

        Supported values: MAXIMIZE_CONVERSIONS, MAXIMIZE_CONVERSION_VALUE,
        MAXIMIZE_CLICKS, TARGET_SPEND.
        """
        # Map strategy name → Campaign proto field name (oneof bidding_scheme).
        _STRATEGY_FIELD: dict[str, str] = {
            "MAXIMIZE_CONVERSIONS": "maximize_conversions",
            "MAXIMIZE_CONVERSION_VALUE": "maximize_conversion_value",
            "MAXIMIZE_CLICKS": "maximize_clicks",
            "TARGET_SPEND": "target_spend",
        }
        field_name = _STRATEGY_FIELD.get(bidding_strategy.upper())
        if field_name is None:
            raise GoogleAdsUnavailable(
                f"Unsupported bidding strategy for automated switching: {bidding_strategy}"
            )
        try:
            client = self._build_client(refresh_token)
            campaign_service = client.get_service("CampaignService")
            resource_name = campaign_service.campaign_path(
                customer_id.replace("-", ""), campaign_id
            )
            operation = client.get_type("CampaignOperation")
            campaign = operation.update
            campaign.resource_name = resource_name
            # For proto3 oneof fields, CopyFrom an empty instance of the same
            # message type marks the variant as selected without setting any
            # sub-fields (uses defaults, which is correct for MAXIMIZE_CONVERSIONS
            # and MAXIMIZE_CLICKS without a target CPA/ROAS).
            sub_msg = getattr(campaign, field_name)
            sub_msg.CopyFrom(type(sub_msg)())
            from google.protobuf import field_mask_pb2
            operation.update_mask.CopyFrom(
                field_mask_pb2.FieldMask(paths=[field_name])
            )
            campaign_service.mutate_campaigns(
                customer_id=customer_id.replace("-", ""),
                operations=[operation],
            )
            logger.info(
                "campaign bidding strategy changed",
                customer_id=customer_id,
                campaign_id=campaign_id,
                bidding_strategy=bidding_strategy,
            )
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("set_campaign_bidding_strategy", exc) from exc

    async def create_campaign_sitelinks(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        sitelinks: list[dict[str, str]],
    ) -> list[str]:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            asset_service = client.get_service("AssetService")
            campaign_asset_service = client.get_service("CampaignAssetService")
            campaign_rn = client.get_service("CampaignService").campaign_path(cid, campaign_id)

            asset_ops = []
            for sl in sitelinks:
                op = client.get_type("AssetOperation")
                a = op.create
                a.sitelink_asset.link_text = sl.get("link_text", "")
                a.sitelink_asset.description1 = sl.get("description1", "")
                a.sitelink_asset.description2 = sl.get("description2", "")
                a.final_urls.append(sl.get("final_url", "https://example.com"))
                asset_ops.append(op)

            asset_rns = [r.resource_name for r in asset_service.mutate_assets(customer_id=cid, operations=asset_ops).results]

            ca_ops = []
            for asset_rn in asset_rns:
                op = client.get_type("CampaignAssetOperation")
                ca = op.create
                ca.campaign = campaign_rn
                ca.asset = asset_rn
                ca.field_type = client.enums.AssetFieldTypeEnum.SITELINK
                ca_ops.append(op)

            ca_rns = [r.resource_name for r in campaign_asset_service.mutate_campaign_assets(customer_id=cid, operations=ca_ops).results]
            logger.info("sitelinks created", customer_id=customer_id, count=len(ca_rns))
            return ca_rns
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("create_campaign_sitelinks", exc) from exc

    async def create_campaign_callouts(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        callout_texts: list[str],
    ) -> list[str]:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            asset_service = client.get_service("AssetService")
            campaign_asset_service = client.get_service("CampaignAssetService")
            campaign_rn = client.get_service("CampaignService").campaign_path(cid, campaign_id)

            asset_ops = []
            for text in callout_texts:
                op = client.get_type("AssetOperation")
                op.create.callout_asset.callout_text = text
                asset_ops.append(op)

            asset_rns = [r.resource_name for r in asset_service.mutate_assets(customer_id=cid, operations=asset_ops).results]

            ca_ops = []
            for asset_rn in asset_rns:
                op = client.get_type("CampaignAssetOperation")
                ca = op.create
                ca.campaign = campaign_rn
                ca.asset = asset_rn
                ca.field_type = client.enums.AssetFieldTypeEnum.CALLOUT
                ca_ops.append(op)

            ca_rns = [r.resource_name for r in campaign_asset_service.mutate_campaign_assets(customer_id=cid, operations=ca_ops).results]
            logger.info("callouts created", customer_id=customer_id, count=len(ca_rns))
            return ca_rns
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("create_campaign_callouts", exc) from exc

    async def create_campaign_structured_snippets(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        header: str,
        values: list[str],
    ) -> list[str]:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            asset_service = client.get_service("AssetService")
            campaign_asset_service = client.get_service("CampaignAssetService")
            campaign_rn = client.get_service("CampaignService").campaign_path(cid, campaign_id)

            op = client.get_type("AssetOperation")
            a = op.create
            a.structured_snippet_asset.header = header
            for v in values:
                a.structured_snippet_asset.values.append(v)
            asset_rns = [r.resource_name for r in asset_service.mutate_assets(customer_id=cid, operations=[op]).results]

            ca_ops = []
            for asset_rn in asset_rns:
                op2 = client.get_type("CampaignAssetOperation")
                ca = op2.create
                ca.campaign = campaign_rn
                ca.asset = asset_rn
                ca.field_type = client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET
                ca_ops.append(op2)

            ca_rns = [r.resource_name for r in campaign_asset_service.mutate_campaign_assets(customer_id=cid, operations=ca_ops).results]
            logger.info("structured snippets created", customer_id=customer_id, count=len(ca_rns))
            return ca_rns
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("create_campaign_structured_snippets", exc) from exc

    async def set_device_bid_modifier(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        bid_modifier: float,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            campaign_criterion_service = client.get_service("CampaignCriterionService")
            op = client.get_type("CampaignCriterionOperation")
            criterion = op.create
            criterion.campaign = client.get_service("CampaignService").campaign_path(cid, campaign_id)
            criterion.device.type_ = client.enums.DeviceEnum.MOBILE
            criterion.bid_modifier = bid_modifier
            campaign_criterion_service.mutate_campaign_criteria(customer_id=cid, operations=[op])
            logger.info("device bid modifier set", customer_id=customer_id, campaign_id=campaign_id, bid_modifier=bid_modifier)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("set_device_bid_modifier", exc) from exc

    async def remove_device_bid_modifier(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            campaign_criterion_service = client.get_service("CampaignCriterionService")
            ga_service = client.get_service("GoogleAdsService")
            query = (
                f"SELECT campaign_criterion.resource_name FROM campaign_criterion "
                f"WHERE campaign_criterion.campaign = 'customers/{cid}/campaigns/{campaign_id}' "
                f"AND campaign_criterion.type = 'DEVICE' "
                f"AND campaign_criterion.device.type = 'MOBILE'"
            )
            response = ga_service.search(customer_id=cid, query=query)
            ops = []
            for row in response:
                op = client.get_type("CampaignCriterionOperation")
                op.remove = row.campaign_criterion.resource_name
                ops.append(op)
            if ops:
                campaign_criterion_service.mutate_campaign_criteria(customer_id=cid, operations=ops)
            logger.info("device bid modifier removed", customer_id=customer_id, campaign_id=campaign_id)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("remove_device_bid_modifier", exc) from exc

    async def remove_campaign_negative_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            ga_service = client.get_service("GoogleAdsService")
            campaign_criterion_service = client.get_service("CampaignCriterionService")
            match_type_enum = getattr(client.enums.KeywordMatchTypeEnum, match_type, None)
            query = (
                f"SELECT campaign_criterion.resource_name FROM campaign_criterion "
                f"WHERE campaign_criterion.campaign = 'customers/{cid}/campaigns/{campaign_id}' "
                f"AND campaign_criterion.negative = TRUE "
                f"AND campaign_criterion.keyword.text = '{keyword_text}'"
            )
            response = ga_service.search(customer_id=cid, query=query)
            ops = []
            for row in response:
                op = client.get_type("CampaignCriterionOperation")
                op.remove = row.campaign_criterion.resource_name
                ops.append(op)
            if ops:
                campaign_criterion_service.mutate_campaign_criteria(customer_id=cid, operations=ops)
            logger.info("campaign negative keyword removed", customer_id=customer_id, keyword=keyword_text)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("remove_campaign_negative_keyword", exc) from exc

    async def add_campaign_negative_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            campaign_criterion_service = client.get_service("CampaignCriterionService")
            op = client.get_type("CampaignCriterionOperation")
            criterion = op.create
            criterion.campaign = client.get_service("CampaignService").campaign_path(cid, campaign_id)
            criterion.negative = True
            criterion.keyword.text = keyword_text
            criterion.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, match_type)
            campaign_criterion_service.mutate_campaign_criteria(customer_id=cid, operations=[op])
            logger.info("campaign negative keyword added", customer_id=customer_id, keyword=keyword_text)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("add_campaign_negative_keyword", exc) from exc

    async def set_target_cpa(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        target_cpa_micros: int,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            campaign_service = client.get_service("CampaignService")
            op = client.get_type("CampaignOperation")
            campaign = op.update
            campaign.resource_name = campaign_service.campaign_path(cid, campaign_id)
            campaign.target_cpa.target_cpa_micros = target_cpa_micros
            from google.protobuf import field_mask_pb2
            op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["target_cpa.target_cpa_micros"]))
            campaign_service.mutate_campaigns(customer_id=cid, operations=[op])
            logger.info("target CPA set", customer_id=customer_id, campaign_id=campaign_id, target_cpa_micros=target_cpa_micros)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("set_target_cpa", exc) from exc

    async def set_ad_schedule_bid_modifier(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        hour_of_day: int,
        bid_modifier: float,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            campaign_criterion_service = client.get_service("CampaignCriterionService")
            # Create criteria for all 7 days for the given hour
            ops = []
            for day in range(2, 9):  # MONDAY=2 through SUNDAY=8
                op = client.get_type("CampaignCriterionOperation")
                criterion = op.create
                criterion.campaign = client.get_service("CampaignService").campaign_path(cid, campaign_id)
                criterion.ad_schedule.day_of_week = day
                criterion.ad_schedule.start_hour = hour_of_day
                criterion.ad_schedule.end_hour = (hour_of_day + 1) % 24
                criterion.ad_schedule.start_minute = client.enums.MinuteOfHourEnum.ZERO
                criterion.ad_schedule.end_minute = client.enums.MinuteOfHourEnum.ZERO
                criterion.bid_modifier = bid_modifier
                ops.append(op)
            campaign_criterion_service.mutate_campaign_criteria(customer_id=cid, operations=ops)
            logger.info("ad schedule set", customer_id=customer_id, campaign_id=campaign_id, hour=hour_of_day)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("set_ad_schedule_bid_modifier", exc) from exc

    async def remove_ad_schedule_criterion(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        hour_of_day: int,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            campaign_criterion_service = client.get_service("CampaignCriterionService")
            ga_service = client.get_service("GoogleAdsService")
            query = (
                f"SELECT campaign_criterion.resource_name FROM campaign_criterion "
                f"WHERE campaign_criterion.campaign = 'customers/{cid}/campaigns/{campaign_id}' "
                f"AND campaign_criterion.type = 'AD_SCHEDULE' "
                f"AND campaign_criterion.ad_schedule.start_hour = {hour_of_day}"
            )
            response = ga_service.search(customer_id=cid, query=query)
            ops = []
            for row in response:
                op = client.get_type("CampaignCriterionOperation")
                op.remove = row.campaign_criterion.resource_name
                ops.append(op)
            if ops:
                campaign_criterion_service.mutate_campaign_criteria(customer_id=cid, operations=ops)
            logger.info("ad schedule removed", customer_id=customer_id, campaign_id=campaign_id, hour=hour_of_day)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("remove_ad_schedule_criterion", exc) from exc

    async def exclude_geo_location(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        location_id: int,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            campaign_criterion_service = client.get_service("CampaignCriterionService")
            op = client.get_type("CampaignCriterionOperation")
            criterion = op.create
            criterion.campaign = client.get_service("CampaignService").campaign_path(cid, campaign_id)
            criterion.negative = True
            criterion.location.geo_target_constant = f"geoTargetConstants/{location_id}"
            campaign_criterion_service.mutate_campaign_criteria(customer_id=cid, operations=[op])
            logger.info("geo excluded", customer_id=customer_id, campaign_id=campaign_id, location_id=location_id)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("exclude_geo_location", exc) from exc

    async def remove_geo_exclusion(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        location_id: int,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            campaign_criterion_service = client.get_service("CampaignCriterionService")
            ga_service = client.get_service("GoogleAdsService")
            location_rn = f"geoTargetConstants/{location_id}"
            query = (
                f"SELECT campaign_criterion.resource_name FROM campaign_criterion "
                f"WHERE campaign_criterion.campaign = 'customers/{cid}/campaigns/{campaign_id}' "
                f"AND campaign_criterion.negative = TRUE "
                f"AND campaign_criterion.location.geo_target_constant = '{location_rn}'"
            )
            response = ga_service.search(customer_id=cid, query=query)
            ops = []
            for row in response:
                op = client.get_type("CampaignCriterionOperation")
                op.remove = row.campaign_criterion.resource_name
                ops.append(op)
            if ops:
                campaign_criterion_service.mutate_campaign_criteria(customer_id=cid, operations=ops)
            logger.info("geo exclusion removed", customer_id=customer_id, campaign_id=campaign_id, location_id=location_id)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("remove_geo_exclusion", exc) from exc

    async def remove_campaign_assets(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_asset_resource_names: list[str],
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            campaign_asset_service = client.get_service("CampaignAssetService")
            ops = []
            for rn in campaign_asset_resource_names:
                op = client.get_type("CampaignAssetOperation")
                op.remove = rn
                ops.append(op)
            campaign_asset_service.mutate_campaign_assets(customer_id=cid, operations=ops)
            logger.info("campaign assets removed", customer_id=customer_id, count=len(ops))
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_mutation_exc("remove_campaign_assets", exc) from exc
