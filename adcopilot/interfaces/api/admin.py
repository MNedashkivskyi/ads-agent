"""Admin API endpoints — list all clients with recommendation counts."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class AdminClientResponse(BaseModel):
    user_id: str
    email: str
    plan: str
    total_recommendations: int
    pending_recommendations: int
    account_count: int
    created_at: str


def _check_admin(user_id: str, settings: Settings) -> None:
    admin_ids = {uid.strip() for uid in settings.ADMIN_USER_IDS.split(",") if uid.strip()}
    if admin_ids and user_id not in admin_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.get("/clients", response_model=list[AdminClientResponse])
async def list_clients(
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[AdminClientResponse]:
    """Return all users with their recommendation and account counts."""
    _check_admin(current_user, settings)

    from adcopilot.infrastructure.db.models import (
        GoogleAdsAccountModel,
        RecommendationModel,
        UserModel,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            # All users
            users_result = await session.execute(
                select(UserModel).order_by(UserModel.created_at.desc())
            )
            users = users_result.scalars().all()

            if not users:
                return []

            user_ids = [u.id for u in users]

            # Account counts per user
            acct_result = await session.execute(
                select(
                    GoogleAdsAccountModel.user_id,
                    func.count(GoogleAdsAccountModel.id).label("cnt"),
                )
                .where(GoogleAdsAccountModel.user_id.in_(user_ids))
                .group_by(GoogleAdsAccountModel.user_id)
            )
            acct_counts: dict = {str(r.user_id): r.cnt for r in acct_result}

            # Get account ids to join recommendations
            all_accts_result = await session.execute(
                select(GoogleAdsAccountModel.id, GoogleAdsAccountModel.user_id).where(
                    GoogleAdsAccountModel.user_id.in_(user_ids)
                )
            )
            acct_user_map: dict = {str(r.id): str(r.user_id) for r in all_accts_result}

            # Recommendation counts per account
            rec_result = await session.execute(
                select(
                    RecommendationModel.account_id,
                    RecommendationModel.status,
                    func.count(RecommendationModel.id).label("cnt"),
                )
                .where(RecommendationModel.account_id.in_([r.id for r in all_accts_result]))
                .group_by(RecommendationModel.account_id, RecommendationModel.status)
            )

            total_recs: dict[str, int] = {}
            pending_recs: dict[str, int] = {}
            for row in rec_result:
                uid = acct_user_map.get(str(row.account_id), "")
                if not uid:
                    continue
                total_recs[uid] = total_recs.get(uid, 0) + row.cnt
                if row.status == "PENDING":
                    pending_recs[uid] = pending_recs.get(uid, 0) + row.cnt
    finally:
        await engine.dispose()

    return [
        AdminClientResponse(
            user_id=str(u.id),
            email=u.email,
            plan=u.plan,
            total_recommendations=total_recs.get(str(u.id), 0),
            pending_recommendations=pending_recs.get(str(u.id), 0),
            account_count=acct_counts.get(str(u.id), 0),
            created_at=u.created_at.isoformat(),
        )
        for u in users
    ]
