"""Detect website platform from landing page URL signatures."""

from __future__ import annotations

import json
import re
from typing import Literal

import httpx
import structlog

logger = structlog.get_logger(__name__)

Platform = Literal["wordpress", "shopify", "woocommerce", "shoper", "custom"]

_TIMEOUT = httpx.Timeout(10.0)

_SIGNATURES: list[tuple[Platform, list[str]]] = [
    ("shopify", ["cdn.shopify.com", "myshopify.com", "Shopify.theme"]),
    ("woocommerce", ["woocommerce", "wc-ajax", "/wp-content/plugins/woocommerce"]),
    ("wordpress", ["wp-content", "wp-includes", "wp-json", "wordpress"]),
    ("shoper", ["shoper.pl", "shoper-static", "sklep.shoper"]),
]


async def detect_platform(url: str) -> Platform:
    """Fetch URL and detect platform from HTML signatures."""
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Adswise/1.0)"},
        ) as client:
            resp = await client.get(url)
            html = resp.text.lower()
    except Exception as exc:
        logger.warning("platform_detection.fetch_failed", url=url, error=str(exc))
        return "custom"

    for platform, sigs in _SIGNATURES:
        if any(sig.lower() in html for sig in sigs):
            logger.info("platform_detection.detected", url=url, platform=platform)
            return platform

    return "custom"


async def detect_platform_from_final_urls(final_urls_json: str) -> Platform:
    """Parse final_urls_json from AdSnapshot and detect platform."""
    try:
        urls: list[str] = json.loads(final_urls_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return "custom"

    if not urls:
        return "custom"

    return await detect_platform(urls[0])
