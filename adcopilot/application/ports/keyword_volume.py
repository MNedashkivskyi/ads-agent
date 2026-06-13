"""KeywordVolumePort — validate phrases against real search volume.

One interface, several backends (Keyword Planner primary, DataForSEO fallback,
Redis cache in front). Returns ``SearchVolume`` per phrase with the ``is_bucketed``
flag set so the validation orchestrator can route bucketed (range-only) results
to the exact-number fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adcopilot.domain.campaign_intelligence.keywords.value_objects import SearchVolume


@dataclass(frozen=True)
class VolumeRequestContext:
    """Context for a volume lookup. ``refresh_token``/``customer_id`` are only
    used by the Keyword Planner backend (client OAuth); other backends ignore them.
    """

    geo: str = "PL"
    language: str = "pl"
    refresh_token: str | None = None
    customer_id: str | None = None


class KeywordVolumePort(Protocol):
    name: str

    async def fetch_volumes(
        self, phrases: list[str], ctx: VolumeRequestContext
    ) -> dict[str, SearchVolume]:
        """Return ``{phrase: SearchVolume}`` for the resolvable phrases.

        Phrases with no data may be omitted. Never raises a raw SDK/HTTP
        exception — surfaces a typed error or fails open per the adapter contract.
        Implementations must batch to ≤ 1000 phrases per upstream request.
        """
        ...
