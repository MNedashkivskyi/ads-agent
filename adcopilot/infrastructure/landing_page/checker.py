"""Landing page checker — fetches URL and extracts content for QS analysis.

Used during proposal validation (Rule 6 / relevance check) to verify that
campaign keywords appear in the page title, H1, and body text.

Timeout: 5 seconds. If the page takes longer, validation passes with a warning.
"""

from __future__ import annotations

import contextlib
import re
import time
from html.parser import HTMLParser

import httpx
import structlog

logger = structlog.get_logger(__name__)

_TIMEOUT_SECONDS = 5.0
_BODY_SAMPLE_CHARS = 2000


class _ContentExtractor(HTMLParser):
    """Minimal HTML parser that extracts title, first H1, and body text."""

    def __init__(self) -> None:
        super().__init__()
        self.title: str = ""
        self.h1: str = ""
        self.body_text: str = ""
        self._in_title = False
        self._in_h1 = False
        self._in_body = False
        self._skip_tags = {"script", "style", "noscript", "head"}
        self._current_skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._skip_tags:
            self._current_skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "h1" and not self.h1:
            self._in_h1 = True
        if tag == "body":
            self._in_body = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self._skip_tags:
            self._current_skip = max(0, self._current_skip - 1)
        if tag == "title":
            self._in_title = False
        if tag == "h1":
            self._in_h1 = False

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        # Title is inside <head> (skipped), so handle it before the skip guard
        if self._in_title:
            self.title += text
        if self._current_skip:
            return
        if self._in_h1:
            self.h1 += text
        if self._in_body and len(self.body_text) < _BODY_SAMPLE_CHARS:
            self.body_text += " " + text


def _extract_language(html: str) -> str | None:
    """Extract lang attribute from <html lang="...">."""
    m = re.search(r'<html[^>]+lang=["\']([a-z]{2})', html, re.IGNORECASE)
    return m.group(1).lower() if m else None


class LandingPageCheckResult:
    """Result of a landing page HTTP probe with content analysis."""

    def __init__(
        self,
        url: str,
        reachable: bool,
        https: bool,
        load_time_seconds: float | None = None,
        language_detected: str | None = None,
        error_message: str | None = None,
        page_title: str | None = None,
        h1_text: str | None = None,
        body_text_sample: str | None = None,
    ) -> None:
        self.url = url
        self.reachable = reachable
        self.https = https
        self.load_time_seconds = load_time_seconds
        self.language_detected = language_detected
        self.error_message = error_message
        self.page_title = page_title
        self.h1_text = h1_text
        self.body_text_sample = body_text_sample


class LandingPageChecker:
    """Fetches a URL and extracts content for Quality Score relevance analysis."""

    async def check(self, url: str) -> LandingPageCheckResult:
        """Fetch *url*, extract title/H1/body text, measure load time.

        Returns a result even on timeout/error — callers treat errors as warnings.
        """
        is_https = url.startswith("https://")

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=_TIMEOUT_SECONDS,
                headers={"User-Agent": "AdCopilot-validator/1.0"},
            ) as client:
                response = await client.get(url)
            elapsed = time.monotonic() - start

            if response.status_code != 200:
                return LandingPageCheckResult(
                    url=url,
                    reachable=False,
                    https=is_https,
                    load_time_seconds=elapsed,
                    error_message=f"HTTP {response.status_code}",
                )

            html = response.text
            lang = _extract_language(html)

            parser = _ContentExtractor()
            with contextlib.suppress(Exception):
                parser.feed(html)

            return LandingPageCheckResult(
                url=url,
                reachable=True,
                https=is_https,
                load_time_seconds=elapsed,
                language_detected=lang,
                page_title=parser.title.strip() or None,
                h1_text=parser.h1.strip() or None,
                body_text_sample=parser.body_text[:_BODY_SAMPLE_CHARS].strip() or None,
            )

        except httpx.TimeoutException:
            elapsed = time.monotonic() - start
            logger.warning("landing_page_timeout", url=url, elapsed=elapsed)
            return LandingPageCheckResult(
                url=url,
                reachable=False,
                https=is_https,
                load_time_seconds=elapsed,
                error_message="timeout",
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.warning("landing_page_error", url=url, error=str(exc)[:100])
            return LandingPageCheckResult(
                url=url,
                reachable=False,
                https=is_https,
                load_time_seconds=elapsed,
                error_message=str(exc)[:100],
            )
