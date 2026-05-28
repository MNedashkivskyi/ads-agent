"""Port: Conversion tracking checker abstraction."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.launch.conversion_tracking_status import ConversionTrackingStatus


class ConversionTrackingChecker(Protocol):
    async def check(self, refresh_token: str, customer_id: str) -> ConversionTrackingStatus:
        """Check whether a Google Ads account has active conversion tracking.

        Never raises — returns has_conversion_tracking=False on any API error.
        """
        ...
