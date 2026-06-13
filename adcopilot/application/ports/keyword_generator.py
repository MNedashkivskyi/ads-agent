"""KeywordGeneratorPort — produce intent-tagged keyword candidates from an LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GeneratedKeyword:
    """One LLM-generated keyword candidate, tagged by intent-type."""

    phrase: str
    intent: str  # "BRAND" | "INTENT" | "PROBLEM"
    reasoning: str = ""


class KeywordGeneratorPort(Protocol):
    async def generate(
        self,
        *,
        service: str,
        vertical: str,
        problems: list[str],
        intent_allocation: dict[str, int],
        language: str = "pl",
    ) -> list[GeneratedKeyword]:
        """Return intent-tagged keyword candidates.

        Implementations validate the LLM's JSON and retry once on malformed
        output before raising a typed domain error.
        """
        ...
