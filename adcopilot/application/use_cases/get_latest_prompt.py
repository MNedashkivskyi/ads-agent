from __future__ import annotations

from adcopilot.application.ports.prompt_version_repository import PromptVersionRepository


async def get_latest_prompt(repo: PromptVersionRepository, key: str) -> str:
    """Return content of the highest-version prompt for *key*.

    Raises KeyError if no prompt with that key exists — callers must seed
    prompt_versions rows via data migration before using a new prompt key.
    """
    pv = await repo.get_latest(key)
    if pv is None:
        raise KeyError(f"No prompt version found for key: {key!r}")
    return pv.content
