"""CachingKeywordGenerator — skip the Haiku call for near-identical inputs.

Beauty SMBs in the same vertical send nearly identical (service, problems)
material. Caching generation on a hash of those inputs avoids re-paying for a
Haiku call when the result would be the same, cutting cost. A cache hit returns
the stored candidates without invoking the wrapped generator (Phase 7.2).
"""

from __future__ import annotations

import hashlib
import json

import structlog

from adcopilot.application.ports.keyword_generator import GeneratedKeyword, KeywordGeneratorPort
from adcopilot.infrastructure.cache.keyword_volume_cache import RedisLike

logger = structlog.get_logger(__name__)

_KEY_PREFIX = "cie:gencache:kw"


def _cache_key(
    service: str, vertical: str, problems: list[str], allocation: dict[str, int], language: str
) -> str:
    payload = json.dumps(
        {
            "service": service.strip().lower(),
            "vertical": vertical,
            "problems": sorted(p.strip().lower() for p in problems),
            "allocation": dict(sorted(allocation.items())),
            "language": language,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha1(payload.encode()).hexdigest()
    return f"{_KEY_PREFIX}:{digest}"


class CachingKeywordGenerator:
    """Wraps a KeywordGeneratorPort with a read-through Redis cache."""

    def __init__(self, inner: KeywordGeneratorPort, redis: RedisLike, ttl_seconds: int) -> None:
        self._inner = inner
        self._redis = redis
        self._ttl = ttl_seconds

    async def generate(
        self,
        *,
        service: str,
        vertical: str,
        problems: list[str],
        intent_allocation: dict[str, int],
        language: str = "pl",
    ) -> list[GeneratedKeyword]:
        key = _cache_key(service, vertical, problems, intent_allocation, language)
        cached = self._get(key)
        if cached is not None:
            logger.info("cie.gencache.hit", vertical=vertical)
            return cached

        result = await self._inner.generate(
            service=service,
            vertical=vertical,
            problems=problems,
            intent_allocation=intent_allocation,
            language=language,
        )
        self._set(key, result)
        return result

    def _get(self, key: str) -> list[GeneratedKeyword] | None:
        try:
            raw = self._redis.get(key)
        except Exception:  # noqa: BLE001 — cache must never break generation
            return None
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            return [
                GeneratedKeyword(
                    phrase=d["phrase"], intent=d["intent"], reasoning=d.get("reasoning", "")
                )
                for d in data
            ]
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def _set(self, key: str, candidates: list[GeneratedKeyword]) -> None:
        try:
            payload = json.dumps(
                [
                    {"phrase": c.phrase, "intent": c.intent, "reasoning": c.reasoning}
                    for c in candidates
                ],
                ensure_ascii=False,
            )
            self._redis.setex(key, self._ttl, payload)
        except Exception:  # noqa: BLE001
            logger.warning("cie.gencache.set_failed")
