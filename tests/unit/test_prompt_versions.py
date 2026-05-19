"""Tests for prompt versioning infrastructure (CCR-5)."""

from __future__ import annotations

import pytest

from adcopilot.application.use_cases.get_latest_prompt import get_latest_prompt
from adcopilot.domain.prompt_version import PromptVersion, PromptVersionId


class InMemoryPromptVersionRepository:
    def __init__(self) -> None:
        self._store: list[PromptVersion] = []
        self._next_id = 1

    async def save(self, prompt_version: PromptVersion) -> None:
        pv = PromptVersion(
            id=PromptVersionId(self._next_id),
            prompt_key=prompt_version.prompt_key,
            version=prompt_version.version,
            content=prompt_version.content,
            created_at=prompt_version.created_at,
        )
        self._next_id += 1
        self._store.append(pv)

    async def get_latest(self, prompt_key: str) -> PromptVersion | None:
        matches = [p for p in self._store if p.prompt_key == prompt_key]
        if not matches:
            return None
        return max(matches, key=lambda p: p.version)

    async def get_by_version(self, prompt_key: str, version: int) -> PromptVersion | None:
        for p in self._store:
            if p.prompt_key == prompt_key and p.version == version:
                return p
        return None


@pytest.fixture
def repo() -> InMemoryPromptVersionRepository:
    return InMemoryPromptVersionRepository()


@pytest.mark.asyncio
async def test_get_latest_prompt_returns_highest_version(repo: InMemoryPromptVersionRepository) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    await repo.save(PromptVersion(id=PromptVersionId(0), prompt_key="test_key", version=1, content="v1 content", created_at=now))
    await repo.save(PromptVersion(id=PromptVersionId(0), prompt_key="test_key", version=2, content="v2 content", created_at=now))

    result = await get_latest_prompt(repo, "test_key")

    assert result == "v2 content"


@pytest.mark.asyncio
async def test_get_latest_prompt_single_version(repo: InMemoryPromptVersionRepository) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    await repo.save(PromptVersion(id=PromptVersionId(0), prompt_key="single_key", version=1, content="only version", created_at=now))

    result = await get_latest_prompt(repo, "single_key")

    assert result == "only version"


@pytest.mark.asyncio
async def test_get_latest_prompt_raises_for_missing_key(repo: InMemoryPromptVersionRepository) -> None:
    with pytest.raises(KeyError, match="missing_key"):
        await get_latest_prompt(repo, "missing_key")


@pytest.mark.asyncio
async def test_get_by_version_returns_specific_version(repo: InMemoryPromptVersionRepository) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    await repo.save(PromptVersion(id=PromptVersionId(0), prompt_key="test_key", version=1, content="v1", created_at=now))
    await repo.save(PromptVersion(id=PromptVersionId(0), prompt_key="test_key", version=2, content="v2", created_at=now))

    result = await repo.get_by_version("test_key", 1)

    assert result is not None
    assert result.content == "v1"
    assert result.version == 1


@pytest.mark.asyncio
async def test_get_latest_ignores_other_keys(repo: InMemoryPromptVersionRepository) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    await repo.save(PromptVersion(id=PromptVersionId(0), prompt_key="key_a", version=1, content="a1", created_at=now))
    await repo.save(PromptVersion(id=PromptVersionId(0), prompt_key="key_b", version=99, content="b99", created_at=now))

    result = await get_latest_prompt(repo, "key_a")

    assert result == "a1"
