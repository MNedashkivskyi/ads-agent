"""Redis read-through cache for validated keyword volumes.

Keyed on ``(phrase, geo, language)`` with a 30-day TTL. Beauty keywords (and most
SMB-vertical keywords) repeat across nearly every client in the vertical, so the
cross-client hit rate is high and the real DataForSEO cost collapses toward a few
dollars a month. A cache hit returns without any upstream API call.
"""

from __future__ import annotations

import json
from typing import Protocol

import structlog

from adcopilot.domain.campaign_intelligence.keywords.value_objects import SearchVolume

logger = structlog.get_logger(__name__)

_KEY_PREFIX = "cie:kwvol"


class RedisLike(Protocol):
    def get(self, key: str) -> bytes | str | None: ...
    def setex(self, key: str, ttl: int, value: str) -> object: ...


def _key(phrase: str, geo: str, language: str) -> str:
    return f"{_KEY_PREFIX}:{geo.upper()}:{language.lower()}:{phrase.strip().lower()}"


def _encode(v: SearchVolume) -> str:
    return json.dumps(
        {
            "monthly_searches": v.monthly_searches,
            "competition": v.competition,
            "cpc_low_micros": v.cpc_low_micros,
            "cpc_high_micros": v.cpc_high_micros,
            "is_bucketed": v.is_bucketed,
        }
    )


def _decode(raw: bytes | str) -> SearchVolume:
    data = json.loads(raw)
    return SearchVolume(
        monthly_searches=int(data["monthly_searches"]),
        competition=str(data.get("competition", "UNKNOWN")),
        cpc_low_micros=int(data.get("cpc_low_micros", 0)),
        cpc_high_micros=int(data.get("cpc_high_micros", 0)),
        is_bucketed=bool(data.get("is_bucketed", False)),
    )


class KeywordVolumeCache:
    """Read-through cache over a Redis-like client."""

    def __init__(self, redis: RedisLike, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    def get_many(
        self, phrases: list[str], *, geo: str, language: str
    ) -> dict[str, SearchVolume]:
        """Return cached volumes for the phrases that are present."""
        out: dict[str, SearchVolume] = {}
        for phrase in phrases:
            try:
                raw = self._redis.get(_key(phrase, geo, language))
            except Exception as exc:  # noqa: BLE001 — cache must never break flow
                logger.warning("kwvol_cache.get_failed", error=str(exc))
                return out
            if raw is not None:
                try:
                    out[phrase.strip().lower()] = _decode(raw)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
        return out

    def set_many(
        self, volumes: dict[str, SearchVolume], *, geo: str, language: str
    ) -> None:
        for phrase, volume in volumes.items():
            try:
                self._redis.setex(_key(phrase, geo, language), self._ttl, _encode(volume))
            except Exception as exc:  # noqa: BLE001
                logger.warning("kwvol_cache.set_failed", error=str(exc))
                return
