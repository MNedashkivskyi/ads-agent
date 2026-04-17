"""Alert history endpoints."""
from __future__ import annotations

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import Settings, get_settings
from adcopilot.infrastructure.db.models import AlertModel

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["alerts"])


@router.get("/{account_id}/alerts")
async def list_alerts(
    account_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return alert history for an account, newest first."""
    try:
        account_uuid = uuid.UUID(account_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid account_id format")

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(AlertModel)
                .where(AlertModel.account_id == account_uuid)
                .order_by(AlertModel.created_at.desc())
                .limit(min(limit, 200))
                .offset(offset)
            )
            models = result.scalars().all()
    finally:
        await engine.dispose()

    items = [
        {
            "id": str(m.id),
            "account_id": str(m.account_id),
            "kind": m.kind,
            "severity": m.severity,
            "status": m.status,
            "message": m.message,
            "payload": m.payload,
            "created_at": m.created_at.isoformat(),
            "acknowledged_at": m.acknowledged_at.isoformat() if m.acknowledged_at else None,
        }
        for m in models
    ]
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}
