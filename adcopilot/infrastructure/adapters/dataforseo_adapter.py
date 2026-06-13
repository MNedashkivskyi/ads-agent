"""DataForSEO adapter — exact search volume + keyword expansion.

Implements ``KeywordVolumePort`` via ``keywords_data/google_ads/search_volume``
(exact, non-bucketed numbers; stays on the cheap no-clickstream tier). Also
provides ``expand_keywords`` (``keywords_for_keywords``) used by the optional
expansion step (Phase 2) to surface high-volume phrasings the LLM wouldn't invent.

Per-request billing, so batches are capped at 1000 keywords/request and each
request is logged. Fail-open: any error returns ``{}`` / ``[]`` so the pipeline
degrades to Keyword Planner only.
"""

from __future__ import annotations

import base64

import httpx
import structlog

from adcopilot.application.ports.keyword_generator import GeneratedKeyword
from adcopilot.application.ports.keyword_volume import VolumeRequestContext
from adcopilot.config import Settings
from adcopilot.domain.campaign_intelligence.keywords.value_objects import SearchVolume

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.dataforseo.com/v3"
_MAX_PER_REQUEST = 1000
_TIMEOUT = 30.0
_LOCATION_NAMES = {"PL": "Poland"}
_COMPETITION_NAMES = {"LOW": "LOW", "MEDIUM": "MEDIUM", "HIGH": "HIGH"}


class DataForSeoAdapter:
    """Implements ``KeywordVolumePort`` plus keyword expansion via DataForSEO."""

    name = "dataforseo"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._login = settings.DATAFORSEO_LOGIN
        self._password = settings.DATAFORSEO_PASSWORD
        self.request_count = 0  # observable for cost guards / logging

    @property
    def is_configured(self) -> bool:
        return bool(self._login and self._password)

    def _auth_header(self) -> dict[str, str]:
        token = base64.b64encode(f"{self._login}:{self._password}".encode()).decode()
        return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

    async def fetch_volumes(
        self, phrases: list[str], ctx: VolumeRequestContext
    ) -> dict[str, SearchVolume]:
        cleaned = [p.strip() for p in phrases if p and p.strip()]
        if not cleaned or not self.is_configured:
            return {}

        out: dict[str, SearchVolume] = {}
        location = _LOCATION_NAMES.get(ctx.geo.upper(), "Poland")
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for start in range(0, len(cleaned), _MAX_PER_REQUEST):
                batch = cleaned[start : start + _MAX_PER_REQUEST]
                payload = [
                    {
                        "keywords": batch,
                        "location_name": location,
                        "language_code": ctx.language,
                    }
                ]
                try:
                    self.request_count += 1
                    logger.info(
                        "dataforseo.search_volume.request",
                        keywords=len(batch),
                        request_count=self.request_count,
                    )
                    resp = await client.post(
                        f"{_BASE_URL}/keywords_data/google_ads/search_volume/live",
                        headers=self._auth_header(),
                        json=payload,
                    )
                    resp.raise_for_status()
                    out.update(self._parse_volume_response(resp.json()))
                except Exception as exc:  # noqa: BLE001 — fail-open
                    logger.warning("dataforseo.search_volume.failed", error=str(exc))
        return out

    async def expand_keywords(
        self,
        seeds: list[str],
        ctx: VolumeRequestContext,
        *,
        limit: int = 100,
        max_requests: int | None = None,
    ) -> list[GeneratedKeyword]:
        """Expand seeds into real, volume-backed related queries.

        Stops before exceeding ``max_requests`` DataForSEO requests (cost guard).
        Returns candidates flagged ``source='expansion'`` (intent inferred later).
        """
        cleaned = [s.strip() for s in seeds if s and s.strip()]
        if not cleaned or not self.is_configured:
            return []
        location = _LOCATION_NAMES.get(ctx.geo.upper(), "Poland")
        out: list[GeneratedKeyword] = []
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for seed in cleaned:
                if max_requests is not None and self.request_count >= max_requests:
                    logger.info("dataforseo.expand.cost_ceiling_reached")
                    break
                payload = [
                    {
                        "keywords": [seed],
                        "location_name": location,
                        "language_code": ctx.language,
                        "limit": limit,
                    }
                ]
                try:
                    self.request_count += 1
                    resp = await client.post(
                        f"{_BASE_URL}/keywords_data/google_ads/keywords_for_keywords/live",
                        headers=self._auth_header(),
                        json=payload,
                    )
                    resp.raise_for_status()
                    out.extend(self._parse_expansion_response(resp.json()))
                except Exception as exc:  # noqa: BLE001 — fail-open
                    logger.warning("dataforseo.expand.failed", seed=seed, error=str(exc))
        return out

    @staticmethod
    def _iter_results(body: dict) -> list[dict]:
        results: list[dict] = []
        for task in body.get("tasks", []) or []:
            for result in task.get("result", []) or []:
                if isinstance(result, dict):
                    results.append(result)
        return results

    @classmethod
    def _parse_volume_response(cls, body: dict) -> dict[str, SearchVolume]:
        out: dict[str, SearchVolume] = {}
        for result in cls._iter_results(body):
            keyword = str(result.get("keyword", "")).strip().lower()
            if not keyword:
                continue
            volume = int(result.get("search_volume") or 0)
            competition = cls._competition(result)
            out[keyword] = SearchVolume(
                monthly_searches=volume,
                competition=competition,
                cpc_low_micros=cls._to_micros(result.get("low_top_of_page_bid")),
                cpc_high_micros=cls._to_micros(result.get("high_top_of_page_bid")),
                is_bucketed=False,  # DataForSEO returns exact numbers
            )
        return out

    @classmethod
    def _parse_expansion_response(cls, body: dict) -> list[GeneratedKeyword]:
        out: list[GeneratedKeyword] = []
        for result in cls._iter_results(body):
            keyword = str(result.get("keyword", "")).strip().lower()
            if not keyword:
                continue
            # Intent is refined downstream; expansion seeds from INTENT terms so
            # related terms default to INTENT until classified.
            out.append(GeneratedKeyword(phrase=keyword, intent="INTENT", reasoning="expansion"))
        return out

    @staticmethod
    def _competition(result: dict) -> str:
        comp = result.get("competition")
        if isinstance(comp, str):
            return _COMPETITION_NAMES.get(comp.upper(), "UNKNOWN")
        idx = result.get("competition_index")
        if isinstance(idx, int | float):
            return "LOW" if idx < 34 else "MEDIUM" if idx < 67 else "HIGH"
        return "UNKNOWN"

    @staticmethod
    def _to_micros(value: object) -> int:
        try:
            return int(float(value) * 1_000_000) if value is not None else 0
        except (TypeError, ValueError):
            return 0
