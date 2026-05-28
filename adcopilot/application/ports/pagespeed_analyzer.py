"""Port: PageSpeed Insights analyzer abstraction."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.launch.pagespeed_result import PageSpeedResult


class PageSpeedAnalyzer(Protocol):
    async def analyze(self, url: str) -> PageSpeedResult:
        """Analyze a URL with PageSpeed Insights.

        Never raises — unavailable API returns PageSpeedResult(available=False).
        """
        ...
