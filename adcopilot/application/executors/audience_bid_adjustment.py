"""Executor: apply an audience bid modifier to a campaign criterion."""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


async def execute_audience_bid_adjustment(
    account_id: str,
    audience_criterion_id: int,
    campaign_resource_name: str,
    new_bid_modifier: float,
    google_ads_client,  # GoogleAdsClient — typed as Any to avoid hard import
    session: AsyncSession,
) -> dict:
    """Apply a bid modifier to an audience campaign criterion via Google Ads API.

    new_bid_modifier: multiplier e.g. 1.3 = +30%, 0.7 = -30%.
    Valid range accepted by Google Ads: 0.1 – 10.0.
    """
    log = logger.bind(
        account_id=account_id,
        criterion_id=audience_criterion_id,
        campaign_resource_name=campaign_resource_name,
        new_bid_modifier=new_bid_modifier,
    )

    # Clamp to Google Ads-accepted range
    clamped_modifier = max(0.1, min(10.0, new_bid_modifier))
    if clamped_modifier != new_bid_modifier:
        log.warning(
            "audience_bid_adjustment.clamped",
            original=new_bid_modifier,
            clamped=clamped_modifier,
        )
        new_bid_modifier = clamped_modifier

    log.info("audience_bid_adjustment.start")

    try:
        campaign_criterion_service = google_ads_client.get_service("CampaignCriterionService")
        campaign_criterion = google_ads_client.get_type("CampaignCriterion")

        campaign_criterion.campaign = campaign_resource_name
        campaign_criterion.criterion_id = audience_criterion_id
        campaign_criterion.bid_modifier = new_bid_modifier

        operation = google_ads_client.get_type("CampaignCriterionOperation")
        operation.update.CopyFrom(campaign_criterion)
        field_mask = google_ads_client.get_type("FieldMask")
        field_mask.paths.append("bid_modifier")
        operation.update_mask.CopyFrom(field_mask)

        response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=account_id,
            operations=[operation],
        )
        resource_name = response.results[0].resource_name
        log.info("audience_bid_adjustment.applied", resource_name=resource_name)

        return {
            "status": "success",
            "criterion_id": audience_criterion_id,
            "campaign_resource_name": campaign_resource_name,
            "new_bid_modifier": new_bid_modifier,
            "resource_name": resource_name,
        }

    except Exception as exc:
        # Stub fallback: log the operation so it can be retried manually
        log.warning(
            "audience_bid_adjustment.stub_fallback",
            error=str(exc),
            note="Google Ads API unavailable — operation logged only",
        )
        return {
            "status": "stub",
            "criterion_id": audience_criterion_id,
            "campaign_resource_name": campaign_resource_name,
            "new_bid_modifier": new_bid_modifier,
            "error": str(exc),
        }
