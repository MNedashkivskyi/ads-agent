"""Campaign channel-type helpers (breadth — Shopping/PMax).

Most detection rules were written assuming Search. These helpers let budget/
bidding/structure rules skip non-Search campaigns so they don't give Search-shaped
advice on Performance Max / Shopping campaigns (which have no keywords/ad groups
and manage bidding differently).
"""

from __future__ import annotations

SEARCH = "SEARCH"
PERFORMANCE_MAX = "PERFORMANCE_MAX"
SHOPPING = "SHOPPING"


def is_search_campaign(channel_type: str | None) -> bool:
    return (channel_type or "").upper() == SEARCH


def is_pmax(channel_type: str | None) -> bool:
    return (channel_type or "").upper() == PERFORMANCE_MAX


def is_shopping(channel_type: str | None) -> bool:
    return (channel_type or "").upper() == SHOPPING


def is_pmax_or_shopping(channel_type: str | None) -> bool:
    return (channel_type or "").upper() in (PERFORMANCE_MAX, SHOPPING)
