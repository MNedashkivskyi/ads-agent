from __future__ import annotations

from typing import Protocol

from adcopilot.domain.prompt_version import PromptVersion


class PromptVersionRepository(Protocol):
    async def save(self, prompt_version: PromptVersion) -> None: ...

    async def get_latest(self, prompt_key: str) -> PromptVersion | None: ...

    async def get_by_version(self, prompt_key: str, version: int) -> PromptVersion | None: ...
