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
