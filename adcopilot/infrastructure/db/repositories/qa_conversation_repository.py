"""QaConversationRepository — persists and retrieves Q&A conversations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.infrastructure.db.models import QaConversationModel


class QaConversation:
    __slots__ = (
        "id",
        "user_id",
        "account_id",
        "question",
        "answer",
        "context_snapshot",
        "created_at",
    )

    def __init__(
        self,
        id: str,
        user_id: str,
        account_id: str | None,
        question: str,
        answer: str,
        context_snapshot: dict[str, Any] | None,
        created_at: datetime,
    ) -> None:
        self.id = id
        self.user_id = user_id
        self.account_id = account_id
        self.question = question
        self.answer = answer
        self.context_snapshot = context_snapshot
        self.created_at = created_at


def _to_domain(m: QaConversationModel) -> QaConversation:
    return QaConversation(
        id=str(m.id),
        user_id=m.user_id,
        account_id=m.account_id,
        question=m.question,
        answer=m.answer,
        context_snapshot=m.context_snapshot,
        created_at=m.created_at,
    )


class SqlQaConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self,
        user_id: str,
        account_id: str | None,
        question: str,
        answer: str,
        context_snapshot: dict[str, Any] | None = None,
    ) -> QaConversation:
        m = QaConversationModel()
        m.id = uuid.uuid4()
        m.user_id = user_id
        m.account_id = account_id
        m.question = question
        m.answer = answer
        m.context_snapshot = context_snapshot
        self._session.add(m)
        await self._session.flush()
        return _to_domain(m)

    async def list_for_user(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[QaConversation]:
        result = await self._session.execute(
            select(QaConversationModel)
            .where(QaConversationModel.user_id == user_id)
            .order_by(QaConversationModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_to_domain(m) for m in result.scalars()]
