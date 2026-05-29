"""Google PageSpeed Insights API v5 adapter."""

from __future__ import annotations

import asyncio
import time

import httpx
import structlog

from adcopilot.domain.launch.pagespeed_result import PageSpeedResult

logger = structlog.get_logger(__name__)

_API_BASE = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
_TIMEOUT = 15.0
_MIN_INTERVAL = 1.0  # 1 req/sec rate limit

_last_call_time: float = 0.0
_lock = asyncio.Lock()


class GooglePageSpeedAdapter:
    """Calls PageSpeed Insights API v5 with 1 req/sec rate limiting."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def analyze(self, url: str) -> PageSpeedResult:
        global _last_call_time

        async with _lock:
            now = time.monotonic()
            wait = _MIN_INTERVAL - (now - _last_call_time)
            if wait > 0:
                await asyncio.sleep(wait)
            _last_call_time = time.monotonic()

        params: dict[str, str] = {"url": url, "strategy": "mobile"}
        if self._api_key:
            params["key"] = self._api_key

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_API_BASE, params=params)

            if resp.status_code != 200:
                logger.warning("pagespeed: non-200 response", status=resp.status_code, url=url)
                return PageSpeedResult(url=url, available=False)

            data = resp.json()
        except Exception as exc:
            logger.warning("pagespeed: request failed", url=url, error=str(exc))
            return PageSpeedResult(url=url, available=False)

        try:
            categories = data.get("lighthouseResult", {}).get("categories", {})
            perf = categories.get("performance", {})
            score_raw = perf.get("score")
            performance_score = int(score_raw * 100) if score_raw is not None else None

            audits = data.get("lighthouseResult", {}).get("audits", {})
            fcp = audits.get("first-contentful-paint", {})
            lcp = audits.get("largest-contentful-paint", {})
            display_value = lcp.get("displayValue") or fcp.get("displayValue") or ""
            load_time_ms: int | None = None
            if display_value:
                # Parse "2.3 s" or "340 ms"
                import re

                m = re.search(r"([\d.]+)\s*(s|ms)", display_value)
                if m:
                    val = float(m.group(1))
                    load_time_ms = int(val * 1000 if m.group(2) == "s" else val)

            issues: list[str] = []
            for audit_id, audit in audits.items():
                if audit.get("score") is not None and audit.get("score", 1) < 0.5:
                    title = audit.get("title", audit_id)
                    issues.append(title)

            mobile_cat = categories.get("mobile", {})
            mobile_score = mobile_cat.get("score", 0)
            mobile_friendly = bool(mobile_score and mobile_score >= 0.9)

        except Exception as exc:
            logger.warning("pagespeed: parse failed", url=url, error=str(exc))
            return PageSpeedResult(url=url, available=False)

        logger.info(
            "pagespeed: analysis complete",
            url=url,
            score=performance_score,
            load_ms=load_time_ms,
        )
        return PageSpeedResult(
            url=url,
            performance_score=performance_score,
            mobile_friendly=mobile_friendly,
            load_time_ms=load_time_ms,
            issues=issues[:5],
            available=True,
        )
