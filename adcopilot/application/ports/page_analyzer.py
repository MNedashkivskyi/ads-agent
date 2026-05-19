"""PageAnalyzer port — abstracts PageSpeed Insights API calls."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.landing_page_score import LandingPageScore


class PageAnalyzer(Protocol):
    async def analyze(self, url: str) -> LandingPageScore:
        """Fetch PageSpeed Insights data for the given URL and return a LandingPageScore.

        Raises:
            PageAnalyzerError: if the API call fails or the URL is unreachable.
        """
        ...
