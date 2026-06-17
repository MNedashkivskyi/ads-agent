"""Free-audit funnel API (Audit Funnel Phase 0).

Phase 0 exposes session promotion (T0.3): claiming an anonymous audit session
for a freshly signed-up user. Report retrieval, the scan trigger, and the
recovery meter arrive in later phases. The read-only OAuth connect itself lives
in ``oauth.py`` (``/oauth/audit/*``).
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adcopilot.application.use_cases.promote_audit_session import PromoteAuditSessionUseCase
from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/audit", tags=["audit"])


class PromoteRequest(BaseModel):
    user_id: str
    account_id: str


@router.post("/sessions/{session_id}/promote")
async def promote_audit_session(
    session_id: str,
    body: PromoteRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """Claim an anonymous audit session for the signed-up user (T0.3)."""
    if current_user != body.user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.audit_repository import (
        SqlAuditSessionRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            use_case = PromoteAuditSessionUseCase(SqlAuditSessionRepository(session))
            promoted = await use_case.execute(
                session_id=session_id, user_id=body.user_id, account_id=body.account_id
            )
    finally:
        await engine.dispose()

    logger.info(
        "audit.session.promote", session_id=session_id, user_id=body.user_id, promoted=promoted
    )
    return {"session_id": session_id, "promoted": promoted}
