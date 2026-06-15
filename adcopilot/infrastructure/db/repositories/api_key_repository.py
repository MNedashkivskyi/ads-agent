"""Repository for customer API keys (Phase 3 / T3.5)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.api_key import ApiKey
from adcopilot.infrastructure.db.models import ApiKeyModel


def _to_domain(m: ApiKeyModel) -> ApiKey:
    return ApiKey(
        id=str(m.id),
        user_id=m.user_id,
        name=m.name,
        display_prefix=m.display_prefix,
        key_hash=m.key_hash,
        created_at=m.created_at,
        revoked_at=m.revoked_at,
        last_used_at=m.last_used_at,
    )


class SqlApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: str, name: str, display_prefix: str, key_hash: str) -> ApiKey:
        m = ApiKeyModel(
            id=uuid.uuid4(),
            user_id=user_id,
            name=name,
            display_prefix=display_prefix,
            key_hash=key_hash,
        )
        self._session.add(m)
        await self._session.flush()
        return _to_domain(m)

    async def list_for_user(self, user_id: str) -> list[ApiKey]:
        rows = (
            await self._session.execute(
                select(ApiKeyModel)
                .where(ApiKeyModel.user_id == user_id)
                .order_by(ApiKeyModel.created_at.desc())
            )
        ).scalars()
        return [_to_domain(m) for m in rows]

    async def get_active_by_hash(self, key_hash: str) -> ApiKey | None:
        m = (
            await self._session.execute(
                select(ApiKeyModel).where(
                    ApiKeyModel.key_hash == key_hash,
                    ApiKeyModel.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        return _to_domain(m) if m else None

    async def revoke(self, user_id: str, key_id: str) -> bool:
        result = await self._session.execute(
            update(ApiKeyModel)
            .where(
                ApiKeyModel.id == uuid.UUID(key_id),
                ApiKeyModel.user_id == user_id,
                ApiKeyModel.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        return result.rowcount > 0

    async def touch_last_used(self, key_id: str) -> None:
        await self._session.execute(
            update(ApiKeyModel)
            .where(ApiKeyModel.id == uuid.UUID(key_id))
            .values(last_used_at=datetime.now(UTC))
        )
