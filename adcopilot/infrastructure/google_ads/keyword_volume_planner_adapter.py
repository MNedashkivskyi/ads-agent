"""Keyword Planner volume adapter — primary volume source via client OAuth.

Implements ``KeywordVolumePort`` using ``GenerateKeywordHistoricalMetrics`` on the
client's own OAuth'd account (free). Runs the sync google-ads SDK in a thread.

**Bucketed-range guard.** Fresh client accounts (no spend history) cannot return
exact monthly-search numbers — the API yields no usable ``avg_monthly_searches``.
When that happens we mark the result ``is_bucketed=True`` so the validation
orchestrator routes that phrase to the exact-number DataForSEO fallback. Auth
failures surface a typed ``GoogleAdsAuthError`` (not a raw SDK exception).
"""

from __future__ import annotations

import asyncio

import structlog

from adcopilot.application.ports.keyword_volume import VolumeRequestContext
from adcopilot.domain.campaign_intelligence.keywords.value_objects import SearchVolume
from adcopilot.domain.exceptions import GoogleAdsAuthError, GoogleAdsRateLimited
from adcopilot.config import Settings
from adcopilot.infrastructure.google_ads.client import (
    GoogleAdsClientAdapter,
    is_google_auth_error,
    is_rate_limit_error,
)

logger = structlog.get_logger(__name__)

_POLAND_GEO_TARGET = "geoTargetConstants/2616"
_LANGUAGE_CONSTANTS = {
    "pl": "languageConstants/1045",
    "uk": "languageConstants/1036",  # Ukrainian
    "en": "languageConstants/1000",
}
_MAX_PER_REQUEST = 1000
_COMPETITION_NAMES = {0: "UNKNOWN", 1: "UNKNOWN", 2: "LOW", 3: "MEDIUM", 4: "HIGH"}


class GoogleKeywordPlannerVolumeAdapter:
    """Implements ``KeywordVolumePort`` against GenerateKeywordHistoricalMetrics."""

    name = "google_keyword_planner"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = GoogleAdsClientAdapter(settings)

    async def fetch_volumes(
        self, phrases: list[str], ctx: VolumeRequestContext
    ) -> dict[str, SearchVolume]:
        cleaned = [p.strip() for p in phrases if p and p.strip()]
        if not cleaned or not ctx.refresh_token or not ctx.customer_id:
            return {}

        out: dict[str, SearchVolume] = {}
        for start in range(0, len(cleaned), _MAX_PER_REQUEST):
            batch = cleaned[start : start + _MAX_PER_REQUEST]
            out.update(await self._fetch_batch(batch, ctx))
        return out

    async def _fetch_batch(
        self, phrases: list[str], ctx: VolumeRequestContext
    ) -> dict[str, SearchVolume]:
        def _blocking() -> dict[str, SearchVolume]:
            try:
                client = self._client._build_client(ctx.refresh_token or "")
                cid = (ctx.customer_id or "").replace("-", "")
                service = client.get_service("KeywordPlanIdeaService")
                request = client.get_type("GenerateKeywordHistoricalMetricsRequest")
                request.customer_id = cid
                request.language = _LANGUAGE_CONSTANTS.get(ctx.language, _LANGUAGE_CONSTANTS["pl"])
                request.geo_target_constants.append(_POLAND_GEO_TARGET)
                request.keyword_plan_network = (
                    client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
                )
                request.keywords.extend(phrases)

                response = service.generate_keyword_historical_metrics(request=request)
                result: dict[str, SearchVolume] = {}
                for row in response.results:
                    metrics = row.keyword_metrics
                    result[row.text.strip().lower()] = self._to_volume(metrics)
                return result
            except Exception as exc:  # noqa: BLE001
                if is_google_auth_error(exc):
                    raise GoogleAdsAuthError(f"Keyword Planner auth failed: {exc}") from exc
                if is_rate_limit_error(exc):
                    raise GoogleAdsRateLimited(str(exc)) from exc
                logger.warning("kp_volume.failed", error=str(exc))
                return {}

        return await asyncio.wait_for(asyncio.to_thread(_blocking), timeout=60)

    @staticmethod
    def _to_volume(metrics: object) -> SearchVolume:
        avg = getattr(metrics, "avg_monthly_searches", None)
        comp_index = int(getattr(metrics, "competition_index", 0) or 0)
        comp_enum = int(getattr(metrics, "competition", 0) or 0)
        competition = _COMPETITION_NAMES.get(comp_enum, "UNKNOWN")
        if competition == "UNKNOWN" and comp_index:
            competition = "LOW" if comp_index < 34 else "MEDIUM" if comp_index < 67 else "HIGH"
        low = int(getattr(metrics, "low_top_of_page_bid_micros", 0) or 0)
        high = int(getattr(metrics, "high_top_of_page_bid_micros", 0) or 0)
        # No usable exact number from a fresh/low-access account → mark bucketed
        # so the orchestrator falls back to DataForSEO for an exact figure.
        if avg is None:
            return SearchVolume(
                monthly_searches=0,
                competition=competition,
                cpc_low_micros=low,
                cpc_high_micros=high,
                is_bucketed=True,
            )
        return SearchVolume(
            monthly_searches=int(avg),
            competition=competition,
            cpc_low_micros=low,
            cpc_high_micros=high,
            is_bucketed=False,
        )
