"""Google Ads conversion tracking checker adapter."""

from __future__ import annotations

import structlog

from adcopilot.application.ports.conversion_tracking_checker import ConversionTrackingChecker
from adcopilot.domain.launch.conversion_tracking_status import ConversionTrackingStatus

logger = structlog.get_logger(__name__)

_MACRO_CATEGORIES = frozenset({"PURCHASE", "LEAD", "SIGNUP", "PHONE_CALL"})


class GoogleAdsConversionAdapter:
    """Implements ConversionTrackingChecker using the existing Google Ads queries adapter."""

    def __init__(self, google_ads_client) -> None:
        self._client = google_ads_client

    async def check(self, refresh_token: str, customer_id: str) -> ConversionTrackingStatus:
        try:
            actions = await self._client.list_conversion_actions(refresh_token, customer_id)
        except Exception as exc:
            logger.warning(
                "conversion_tracking: API call failed",
                customer_id=customer_id,
                error=str(exc),
            )
            return ConversionTrackingStatus(
                customer_id=customer_id,
                has_conversion_tracking=False,
            )

        active = [
            a
            for a in actions
            if a.status == "ENABLED"
            and a.category in _MACRO_CATEGORIES
            and a.include_in_conversions_metric
        ]

        logger.info(
            "conversion_tracking: check complete",
            customer_id=customer_id,
            total_actions=len(actions),
            active_macro_actions=len(active),
        )

        return ConversionTrackingStatus(
            customer_id=customer_id,
            has_conversion_tracking=bool(active),
            conversion_action_count=len(active),
            active_action_names=[a.name for a in active],
        )
