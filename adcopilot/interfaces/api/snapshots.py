"""Snapshot trigger and status API endpoints."""

import datetime
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.worker.tasks import snapshot_account_task

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["snapshots"])


class SnapshotRequest(BaseModel):
    date: datetime.date | None = None


class SnapshotEnqueueResponse(BaseModel):
    task_id: str
    account_id: str
    snapshot_date: str


class SnapshotStatusResponse(BaseModel):
    account_id: str
    snapshot_date: str | None
    status: str | None
    campaigns: int
    ad_groups: int
    keywords: int
    search_terms: int
    ads: int
    duration_seconds: float | None
    error_message: str | None


@router.post("/{account_id}/snapshots", status_code=202)
async def trigger_snapshot(
    account_id: str,
    body: SnapshotRequest | None = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> SnapshotEnqueueResponse:
    """Manually trigger a snapshot for an account. Returns 202 with task_id."""
    snap_date = (body.date if body and body.date else None) or datetime.date.today()

    task = snapshot_account_task.delay(account_id, snap_date.isoformat())

    logger.info("snapshot enqueued", account_id=account_id, date=snap_date.isoformat())
    return SnapshotEnqueueResponse(
        task_id=task.id,
        account_id=account_id,
        snapshot_date=snap_date.isoformat(),
    )


@router.get("/{account_id}/snapshots/latest")
async def get_latest_snapshot(
    account_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SnapshotStatusResponse:
    """Return the most recent snapshot run record for an account."""
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from sqlalchemy import select

            from adcopilot.infrastructure.db.models import SnapshotRunModel

            result = await session.execute(
                select(SnapshotRunModel)
                .where(SnapshotRunModel.account_id == uuid.UUID(account_id))
                .order_by(SnapshotRunModel.created_at.desc())
                .limit(1)
            )
            run = result.scalar_one_or_none()
    finally:
        await engine.dispose()

    if run is None:
        raise HTTPException(status_code=404, detail="No snapshot runs found for this account")

    return SnapshotStatusResponse(
        account_id=account_id,
        snapshot_date=run.snapshot_date.isoformat() if run.snapshot_date else None,
        status=run.status,
        campaigns=run.campaigns,
        ad_groups=run.ad_groups,
        keywords=run.keywords,
        search_terms=run.search_terms,
        ads=run.ads,
        duration_seconds=run.duration_seconds,
        error_message=run.error_message,
    )
