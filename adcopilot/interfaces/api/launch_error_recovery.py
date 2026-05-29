"""POST /api/proposals/{id}/recover — error recovery for stuck proposals.

Handles edge cases in the campaign creation wizard:
- Reset a FAILED or stuck GENERATING brief back to PROPOSED state
- Re-queue generation if a brief has been GENERATING for >10 minutes
- Mark a brief as ABANDONED (user explicitly cancels)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/proposals", tags=["launch-error-recovery"])

_STALE_GENERATING_MINUTES = 10


class RecoverRequest(BaseModel):
    action: str  # "retry" | "abandon"


class RecoverResponse(BaseModel):
    proposal_id: str | None
    brief_id: str
    status: str
    action_taken: str


@router.post("/{brief_id}/recover", response_model=RecoverResponse)
async def recover_proposal(
    brief_id: str,
    body: RecoverRequest,
    user_id: CurrentUser,
) -> RecoverResponse:
    """Recover a stuck or failed campaign brief.

    Actions:
    - "retry": re-queues generation for FAILED or stale GENERATING briefs
    - "abandon": marks the brief as ABANDONED (user cancels)
    """
    try:
        uuid.UUID(brief_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid brief ID format") from None

    if body.action not in ("retry", "abandon"):
        raise HTTPException(status_code=422, detail="action must be 'retry' or 'abandon'")

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    try:
        async with AsyncSession(engine) as session, session.begin():
            from adcopilot.domain.launch.entities import (
                CampaignBriefId,
                LaunchStatus,
            )
            from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
                SqlCampaignBriefRepository,
            )

            repo = SqlCampaignBriefRepository(session)
            brief = await repo.get(CampaignBriefId(brief_id))

            if brief is None or brief.user_id != user_id:
                raise HTTPException(status_code=404, detail="Brief not found")

            if body.action == "abandon":
                if brief.status == LaunchStatus.ENABLED:
                    raise HTTPException(
                        status_code=409,
                        detail="Cannot abandon an already-live campaign",
                    )
                updated = _replace_brief_status(brief, LaunchStatus.ABANDONED)
                await repo.save(updated)
                logger.info("recover.abandoned", brief_id=brief_id, user_id=user_id)
                return RecoverResponse(
                    brief_id=brief_id,
                    proposal_id=None,
                    status="abandoned",
                    action_taken="abandoned",
                )

            # retry
            if brief.status == LaunchStatus.ENABLED:
                raise HTTPException(
                    status_code=409,
                    detail="Campaign is already live — no recovery needed",
                )
            if brief.status == LaunchStatus.ABANDONED:
                raise HTTPException(
                    status_code=409,
                    detail="Brief was abandoned — create a new one",
                )

            # Check if GENERATING for too long (stale)
            is_stale_generating = brief.status == LaunchStatus.GENERATING and (
                datetime.now(UTC) - brief.created_at
            ) > timedelta(minutes=_STALE_GENERATING_MINUTES)
            if (
                brief.status not in (LaunchStatus.GENERATING, LaunchStatus.PROPOSED)
                and not is_stale_generating
                and brief.status != LaunchStatus.PROPOSED
            ):
                pass  # Already in a retryable state — just re-queue

            # Reset to GENERATING and re-queue
            updated = _replace_brief_status(brief, LaunchStatus.GENERATING)
            await repo.save(updated)
    finally:
        await engine.dispose()

    from adcopilot.interfaces.worker.tasks import generate_campaign_task

    generate_campaign_task.delay(brief_id)

    logger.info("recover.retry_queued", brief_id=brief_id, user_id=user_id)
    return RecoverResponse(
        brief_id=brief_id,
        proposal_id=None,
        status="generating",
        action_taken="retry_queued",
    )


def _replace_brief_status(brief, new_status):
    """Return a copy of brief with updated status (frozen dataclass)."""
    from dataclasses import replace as dc_replace

    return dc_replace(brief, status=new_status)
