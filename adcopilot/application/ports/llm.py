"""LLM client port (Protocol)."""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 400,
        temperature: float = 0.3,
    ) -> str: ...
