"""Google Ads mutations adapter — wraps the google-ads library for write operations."""

from __future__ import annotations

from typing import Any

import structlog

from adcopilot.config import Settings
from adcopilot.domain.exceptions import GoogleAdsUnavailable
from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter

logger = structlog.get_logger(__name__)


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
        except Exception as exc:
            raise GoogleAdsUnavailable(f"pause_keyword failed: {exc}") from exc

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
        except Exception as exc:
            raise GoogleAdsUnavailable(f"pause_ad failed: {exc}") from exc

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
        except Exception as exc:
            raise GoogleAdsUnavailable(f"add_ad_group_negative_keyword failed: {exc}") from exc

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
        except GoogleAdsUnavailable:
            raise
        except Exception as exc:
            raise GoogleAdsUnavailable(f"update_campaign_budget failed: {exc}") from exc

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
        except Exception as exc:
            raise GoogleAdsUnavailable(f"enable_keyword failed: {exc}") from exc

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
        except Exception as exc:
            raise GoogleAdsUnavailable(f"enable_ad failed: {exc}") from exc

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
        except Exception as exc:
            raise GoogleAdsUnavailable(f"remove_ad_group_negative_keyword failed: {exc}") from exc
