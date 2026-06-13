"""AdSurface — the ad slots a hook can occupy, each with its character limit."""

from __future__ import annotations

from enum import StrEnum


class AdSurface(StrEnum):
    HEADLINE = "HEADLINE"
    DESCRIPTION = "DESCRIPTION"
    SITELINK = "SITELINK"
    CALLOUT = "CALLOUT"
    SNIPPET = "SNIPPET"


# Google Ads RSA character limits per surface.
_CHAR_LIMITS: dict[AdSurface, int] = {
    AdSurface.HEADLINE: 30,
    AdSurface.DESCRIPTION: 90,
    AdSurface.SITELINK: 25,
    AdSurface.CALLOUT: 25,
    AdSurface.SNIPPET: 25,
}


def char_limit(surface: AdSurface) -> int:
    """Maximum character length allowed for a hook on this surface."""
    return _CHAR_LIMITS[surface]


def within_limit(surface: AdSurface, text: str) -> bool:
    return len(text) <= char_limit(surface)
