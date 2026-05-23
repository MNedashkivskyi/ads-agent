"""PageSpeed Insights adapter — implements PageAnalyzer port."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import structlog

from adcopilot.domain.exceptions import PageAnalyzerError
from adcopilot.domain.landing_page_score import CoreWebVitals, LandingPageScore

logger = structlog.get_logger(__name__)

_PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
_TIMEOUT = 60.0  # PSI can be slow on first cold fetch


def _safe_int(value: float | None) -> int:
    if value is None:
        return 0
    return max(0, min(100, round(value * 100)))


def _metric_ms(audits: dict, key: str) -> float | None:
    item = audits.get(key, {})
    display = item.get("displayValue", "")
    numeric = item.get("numericValue")
    if numeric is not None:
        return float(numeric)
    # fallback: parse "1,234 ms" or "1.2 s"
    try:
        clean = display.replace(",", "").replace(" ", "").strip()
        if clean.endswith("ms"):
            return float(clean[:-2].strip())
        if clean.endswith("s"):
            return float(clean[:-1].strip()) * 1000
    except (ValueError, AttributeError):
        pass
    return None


def _parse_cwv(audits: dict) -> CoreWebVitals:
    return CoreWebVitals(
        lcp_ms=_metric_ms(audits, "largest-contentful-paint"),
        fcp_ms=_metric_ms(audits, "first-contentful-paint"),
        cls_score=audits.get("cumulative-layout-shift", {}).get("numericValue"),
        ttfb_ms=_metric_ms(audits, "server-response-time"),
        tbt_ms=_metric_ms(audits, "total-blocking-time"),
        speed_index_ms=_metric_ms(audits, "speed-index"),
    )


def _parse_score(data: dict) -> LandingPageScore:
    categories = data.get("lighthouseResult", {}).get("categories", {})
    audits = data.get("lighthouseResult", {}).get("audits", {})
    loading_exp = data.get("loadingExperience", {})

    performance = _safe_int(categories.get("performance", {}).get("score"))
    accessibility = _safe_int(categories.get("accessibility", {}).get("score"))
    seo = _safe_int(categories.get("seo", {}).get("score"))
    best_practices = _safe_int(categories.get("best-practices", {}).get("score"))

    # mobile-friendly heuristic: CrUX overall category FAST or AVERAGE
    overall_category = loading_exp.get("overall_category", "")
    mobile_friendly = overall_category in ("FAST", "AVERAGE")

    return LandingPageScore(
        url=data.get("id", ""),
        performance_score=performance,
        accessibility_score=accessibility,
        seo_score=seo,
        best_practices_score=best_practices,
        mobile_friendly=mobile_friendly,
        core_web_vitals=_parse_cwv(audits),
        recommendations_pl=[],  # filled by LandingPageScoreUseCase
        scored_at=datetime.now(UTC),
        raw_pagespeed=data,
    )


class PageSpeedAdapter:
    """Calls Google PageSpeed Insights API v5."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def analyze(self, url: str) -> LandingPageScore:
        params: dict = {
            "url": url,
            "strategy": "mobile",
            "category": ["performance", "accessibility", "seo", "best-practices"],
        }
        if self._api_key:
            params["key"] = self._api_key

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(_PSI_ENDPOINT, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise PageAnalyzerError(f"PageSpeed timeout for {url}") from exc
        except httpx.HTTPStatusError as exc:
            raise PageAnalyzerError(
                f"PageSpeed API error {exc.response.status_code} for {url}"
            ) from exc
        except Exception as exc:
            raise PageAnalyzerError(f"PageSpeed unexpected error for {url}: {exc}") from exc

        logger.info(
            "pagespeed.analyzed",
            url=url,
            score=_safe_int(
                data.get("lighthouseResult", {})
                .get("categories", {})
                .get("performance", {})
                .get("score")
            ),
        )
        return _parse_score(data)
