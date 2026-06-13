"""validate_keyword_volumes — cache → KP → bucketed-guard → DataForSEO.

The orchestration that turns generated candidates into volume-backed, ranked
keywords. For every candidate phrase:

1. **Cache** — a 30-day Redis hit returns with no API call.
2. **Keyword Planner** (client OAuth, free) — primary source.
3. **Bucketed guard** — if KP returns a range-only (``is_bucketed``) or missing
   number for a phrase, *that phrase only* is routed to the fallback.
4. **DataForSEO** — exact-number fallback (per-request billing).

Newly resolved exact volumes are written through the cache. Candidates with
viable volume become ``validated``; the rest ``rejected``. Idempotent: a re-run
hits the cache and never re-charges a previously resolved phrase. Rate-limit
errors retry with backoff, then fail cleanly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import structlog

from adcopilot.application.ports.cie_keyword_repository import CieKeywordRepository
from adcopilot.application.ports.keyword_volume import KeywordVolumePort, VolumeRequestContext
from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import (
    KeywordCandidate,
    KeywordStatus,
)
from adcopilot.domain.campaign_intelligence.keywords.keyword_run import (
    KeywordRun,
    KeywordRunStatus,
)
from adcopilot.domain.campaign_intelligence.keywords.value_objects import SearchVolume
from adcopilot.domain.exceptions import GoogleAdsRateLimited
from adcopilot.infrastructure.cache.keyword_volume_cache import KeywordVolumeCache

logger = structlog.get_logger(__name__)

_MAX_RATE_LIMIT_RETRIES = 3


class ValidateKeywordVolumesUseCase:
    def __init__(
        self,
        cache: KeywordVolumeCache,
        primary: KeywordVolumePort,
        fallback: KeywordVolumePort,
        repo: CieKeywordRepository,
        *,
        geo: str = "PL",
        min_viable_volume: int = 10,
        keep_all: bool = False,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._cache = cache
        self._primary = primary
        self._fallback = fallback
        self._repo = repo
        self._geo = geo
        self._min_viable_volume = min_viable_volume
        # When True, every candidate is kept (status=validated) with whatever
        # volume was found (0 if none) rather than rejecting non-viable ones.
        # Used by the interactive launch step so the comparison is always
        # populated even if the volume APIs are unavailable in this environment.
        self._keep_all = keep_all
        self._sleep = sleep

    async def run(
        self,
        run: KeywordRun,
        *,
        refresh_token: str | None = None,
        customer_id: str | None = None,
    ) -> KeywordRun:
        if run.id is None:
            raise ValueError("run must be persisted before validation")

        await self._repo.set_run_status(run.id, KeywordRunStatus.VALIDATING)
        candidates = await self._repo.list_candidates(run.id)
        phrases = [c.phrase for c in candidates]
        ctx = VolumeRequestContext(
            geo=self._geo,
            language=run.language,
            refresh_token=refresh_token,
            customer_id=customer_id,
        )

        try:
            resolved = await self._resolve_volumes(phrases, ctx)
        except GoogleAdsRateLimited as exc:
            await self._repo.set_run_status(run.id, KeywordRunStatus.FAILED, str(exc))
            run.status = KeywordRunStatus.FAILED
            run.error = str(exc)
            raise

        for candidate in candidates:
            volume = resolved.get(candidate.phrase.strip().lower())
            if self._keep_all:
                candidate.volume = volume or SearchVolume(monthly_searches=0)
                candidate.status = KeywordStatus.VALIDATED
            elif volume is None:
                candidate.mark_rejected()
            else:
                self._apply_volume(candidate, volume)
            await self._repo.save_candidate(candidate)

        await self._repo.set_run_status(run.id, KeywordRunStatus.READY)
        run.status = KeywordRunStatus.READY
        validated = sum(1 for c in candidates if c.is_validated)
        logger.info(
            "cie.keywords.validated", run_id=run.id, validated=validated, total=len(candidates)
        )
        return run

    def _apply_volume(self, candidate: KeywordCandidate, volume: SearchVolume) -> None:
        # Respect the run-level viability threshold even if it differs from the
        # VO default.
        candidate.volume = volume
        if volume.monthly_searches >= self._min_viable_volume:
            candidate.mark_validated(volume)
        else:
            candidate.mark_rejected()

    async def _resolve_volumes(
        self, phrases: list[str], ctx: VolumeRequestContext
    ) -> dict[str, SearchVolume]:
        resolved: dict[str, SearchVolume] = {}
        # 1. Cache
        cached = self._cache.get_many(phrases, geo=ctx.geo, language=ctx.language)
        resolved.update(cached)
        misses = [p for p in phrases if p.strip().lower() not in resolved]
        if not misses:
            return resolved

        newly_cached: dict[str, SearchVolume] = {}

        # 2. Keyword Planner primary (with rate-limit retry/backoff)
        kp = await self._with_rate_limit_retry(
            lambda: self._primary.fetch_volumes(misses, ctx), label="kp"
        )
        fallback_needed: list[str] = []
        for phrase in misses:
            key = phrase.strip().lower()
            sv = kp.get(key)
            # 3. Bucketed guard — route only bucketed/missing/zero phrases onward.
            if sv is not None and not sv.is_bucketed and sv.monthly_searches > 0:
                resolved[key] = sv
                newly_cached[key] = sv
            else:
                fallback_needed.append(phrase)

        # 4. DataForSEO fallback (exact numbers) for the bucketed phrases only.
        if fallback_needed:
            df = await self._with_rate_limit_retry(
                lambda: self._fallback.fetch_volumes(fallback_needed, ctx), label="dataforseo"
            )
            for phrase in fallback_needed:
                key = phrase.strip().lower()
                sv = df.get(key)
                if sv is not None:
                    resolved[key] = sv
                    newly_cached[key] = sv

        # Write through only the newly resolved exact volumes.
        self._cache.set_many(newly_cached, geo=ctx.geo, language=ctx.language)
        return resolved

    async def _with_rate_limit_retry(
        self,
        fn: Callable[[], Awaitable[dict[str, SearchVolume]]],
        *,
        label: str,
    ) -> dict[str, SearchVolume]:
        last: GoogleAdsRateLimited | None = None
        for attempt in range(_MAX_RATE_LIMIT_RETRIES):
            try:
                return await fn()
            except GoogleAdsRateLimited as exc:
                last = exc
                backoff = 2.0**attempt
                logger.warning(
                    "cie.keywords.rate_limited", source=label, attempt=attempt + 1, backoff=backoff
                )
                await self._sleep(backoff)
        assert last is not None
        raise last
