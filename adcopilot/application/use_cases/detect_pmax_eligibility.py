"""Use case: detect whether an account is eligible for a Performance Max campaign.

Eligibility requires:
1. The account's vertical is "ecommerce" (or contains "ecommerce").
2. The account has at least one linked Merchant Center feed.

When both conditions are met the caller should offer PMax to the user before
starting the standard Search campaign interview flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class MerchantCenterFeedProvider(Protocol):
    """Port — returns linked Merchant Center feeds for a customer."""

    async def query_merchant_center_feed(
        self,
        refresh_token: str,
        customer_id: str,
    ) -> list[dict[str, object]]: ...


@dataclass(frozen=True)
class PMaxEligibilityResult:
    eligible: bool
    vertical: str
    feeds: list[dict[str, object]]
    """Non-empty when eligible is True."""


_ECOMMERCE_VERTICALS = frozenset({"ecommerce", "e-commerce", "sklep", "sklep internetowy"})


def _is_ecommerce(vertical: str) -> bool:
    v = vertical.lower().strip()
    return v in _ECOMMERCE_VERTICALS or "ecommerce" in v or "e-commerce" in v


class DetectPMaxEligibilityUseCase:
    """Check if an account should be offered a PMax campaign.

    Args:
        feed_provider: Port that queries the Google Ads API for MC feeds.
    """

    def __init__(self, feed_provider: MerchantCenterFeedProvider) -> None:
        self._provider = feed_provider

    async def run(
        self,
        vertical: str,
        refresh_token: str,
        customer_id: str,
    ) -> PMaxEligibilityResult:
        """Return eligibility result.

        Does *not* raise — on API errors returns eligible=False so the caller
        can fall back to the standard Search campaign flow.
        """
        if not _is_ecommerce(vertical):
            return PMaxEligibilityResult(eligible=False, vertical=vertical, feeds=[])

        try:
            feeds = await self._provider.query_merchant_center_feed(
                refresh_token=refresh_token,
                customer_id=customer_id,
            )
        except Exception:
            # Graceful degradation: if feed check fails, fall back to Search
            return PMaxEligibilityResult(eligible=False, vertical=vertical, feeds=[])

        active_feeds = [f for f in feeds if str(f.get("status", "")).upper() == "ENABLED"]
        if not active_feeds:
            return PMaxEligibilityResult(eligible=False, vertical=vertical, feeds=[])

        return PMaxEligibilityResult(eligible=True, vertical=vertical, feeds=active_feeds)
