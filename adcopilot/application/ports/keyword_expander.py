"""KeywordExpanderPort — expand seeds into real, volume-backed related queries."""

from __future__ import annotations

from typing import Protocol

from adcopilot.application.ports.keyword_generator import GeneratedKeyword
from adcopilot.application.ports.keyword_volume import VolumeRequestContext


class KeywordExpanderPort(Protocol):
    is_configured: bool

    async def expand_keywords(
        self,
        seeds: list[str],
        ctx: VolumeRequestContext,
        *,
        limit: int = 100,
        max_requests: int | None = None,
    ) -> list[GeneratedKeyword]:
        """Expand seeds into related queries, stopping before ``max_requests``."""
        ...
