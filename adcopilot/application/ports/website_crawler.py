"""Port: website crawler abstraction."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.launch.website_intelligence import WebsiteIntelligence


class WebsiteCrawler(Protocol):
    async def crawl(self, url: str) -> WebsiteIntelligence:
        """Fetch and parse a website, returning extracted intelligence.

        Never raises — failed crawls return a WebsiteIntelligence with
        crawl_status=FAILED so callers can continue without a website.
        """
        ...
