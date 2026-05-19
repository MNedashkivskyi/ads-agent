from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.prompt_version import PromptVersion, PromptVersionId
from adcopilot.infrastructure.db.models import PromptVersionModel


def _to_domain(m: PromptVersionModel) -> PromptVersion:
    return PromptVersion(
        id=PromptVersionId(m.id),
        prompt_key=m.prompt_key,
        version=m.version,
        content=m.content,
        created_at=m.created_at,
    )


class SqlPromptVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, prompt_version: PromptVersion) -> None:
        m = PromptVersionModel()
        m.prompt_key = prompt_version.prompt_key
        m.version = prompt_version.version
        m.content = prompt_version.content
        self._session.add(m)

    async def get_latest(self, prompt_key: str) -> PromptVersion | None:
        result = await self._session.execute(
            select(PromptVersionModel)
            .where(PromptVersionModel.prompt_key == prompt_key)
            .order_by(PromptVersionModel.version.desc())
            .limit(1)
        )
        m = result.scalar_one_or_none()
        return _to_domain(m) if m else None

    async def get_by_version(self, prompt_key: str, version: int) -> PromptVersion | None:
        result = await self._session.execute(
            select(PromptVersionModel).where(
                PromptVersionModel.prompt_key == prompt_key,
                PromptVersionModel.version == version,
            )
        )
        m = result.scalar_one_or_none()
        return _to_domain(m) if m else None
