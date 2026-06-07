"""Notifications API endpoints."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    notification_type: str
    title: str
    body: str
    metadata: dict
    read_at: str | None
    created_at: str


class UnreadCountResponse(BaseModel):
    unread_count: int


def _parse_uuid(value: str, field: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {field} format") from exc


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    user_id: str,
    current_user: CurrentUser,
    limit: int = 50,
    offset: int = 0,
    settings: Annotated[Settings, Depends(get_settings)] = ...,
) -> list[NotificationResponse]:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.notification_repository import (
        SqlNotificationRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlNotificationRepository(session)
            notifications = await repo.list_for_user(user_id, limit=limit, offset=offset)
    finally:
        await engine.dispose()

    return [
        NotificationResponse(
            id=n.id,
            user_id=n.user_id,
            notification_type=n.notification_type.value,
            title=n.title,
            body=n.body,
            metadata=n.metadata,
            read_at=n.read_at.isoformat() if n.read_at else None,
            created_at=n.created_at.isoformat(),
        )
        for n in notifications
    ]


@router.patch("/{notification_id}/read", status_code=204)
async def mark_notification_read(
    notification_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)] = ...,
) -> None:
    _parse_uuid(notification_id, "notification_id")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.notification_repository import (
        SqlNotificationRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlNotificationRepository(session)
            notification = await repo.get(notification_id)
            if notification is None:
                raise HTTPException(status_code=404, detail="Notification not found")
            if str(notification.user_id) != current_user:
                raise HTTPException(status_code=403, detail="Access denied")
            await repo.mark_read(notification_id)
    finally:
        await engine.dispose()


@router.post("/mark-all-read", status_code=204)
async def mark_all_read(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)] = ...,
) -> None:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.notification_repository import (
        SqlNotificationRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlNotificationRepository(session)
            await repo.mark_all_read(user_id)
    finally:
        await engine.dispose()


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)] = ...,
) -> UnreadCountResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.notification_repository import (
        SqlNotificationRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlNotificationRepository(session)
            count = await repo.count_unread(user_id)
    finally:
        await engine.dispose()

    return UnreadCountResponse(unread_count=count)


async def _event_generator(user_id: str, settings: Settings):
    last_count = -1
    while True:
        try:
            from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

            from adcopilot.infrastructure.db.repositories.notification_repository import (
                SqlNotificationRepository,
            )

            engine = create_async_engine(settings.DATABASE_URL)
            try:
                async with AsyncSession(engine) as session, session.begin():
                    repo = SqlNotificationRepository(session)
                    count = await repo.count_unread(user_id)
            finally:
                await engine.dispose()

            if count != last_count:
                last_count = count
                yield f"data: {json.dumps({'unread_count': count})}\n\n"
            else:
                yield ": ping\n\n"
        except Exception as exc:
            logger.warning("sse error", user_id=user_id, error=str(exc))
            yield ": ping\n\n"

        await asyncio.sleep(15)


@router.get("/stream")
async def stream_notifications(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)] = ...,
) -> StreamingResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return StreamingResponse(
        _event_generator(user_id, settings),
        media_type="text/event-stream",
    )
