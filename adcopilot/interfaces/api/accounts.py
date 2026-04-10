"""Google Ads account management endpoints."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import Settings, get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.delete("/{account_id}")
async def disconnect_account(
    account_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Disconnect (soft-delete) a Google Ads account."""
    import uuid as uuid_mod

    from sqlalchemy import select

    from adcopilot.infrastructure.db.models import GoogleAdsAccountModel

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(GoogleAdsAccountModel).where(
                    GoogleAdsAccountModel.id == uuid_mod.UUID(account_id)
                )
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise HTTPException(status_code=404, detail="Account not found")

            # Soft-delete: mark as needs_reauth so it won't receive snapshots
            # and won't appear in active account lists
            model.needs_reauth = True
            await session.commit()
    finally:
        await engine.dispose()

    logger.info("account disconnected", account_id=account_id)
    return {"status": "disconnected"}
