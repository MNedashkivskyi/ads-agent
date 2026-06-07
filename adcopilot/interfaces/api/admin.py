"""Admin API endpoints — list all clients with recommendation counts."""

from __future__ import annotations

import uuid
from datetime import date
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
    # Fail closed: an empty allow-list means NO admins. Previously this
    # short-circuited (`if admin_ids and ...`), making every authenticated
    # user an admin whenever ADMIN_USER_IDS was unset (the default).
    if user_id not in admin_ids:
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


class SeedDemoRequest(BaseModel):
    # If omitted, demo accounts are attached to the calling admin user (Approach A),
    # so one login manages all of them via the account switcher.
    owner_email: str | None = None
    accounts: int | None = None  # how many demo businesses (default: all 11)
    days: int = 56
    end_date: str | None = None  # YYYY-MM-DD; defaults to today
    reset: bool = True  # wipe prior [DEMO] data first (owner-safe)
    force: bool = False  # allow running when ENV=production


class SeedDemoResponse(BaseModel):
    owner_user_id: str
    owner_email: str | None
    total_rows: int
    counts: dict[str, int]


@router.post("/demo/seed", response_model=SeedDemoResponse)
async def seed_demo_accounts(
    body: SeedDemoRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SeedDemoResponse:
    """Seed scenario-rich demo accounts (for Railway, where the CLI can't run).

    By default the 11 demo accounts are owned by the calling admin user, so they
    all show up in that user's account switcher and can be managed separately.
    """
    _check_admin(current_user, settings)

    if settings.is_production and not body.force:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refusing to seed demo data while ENV=production. Pass force=true to override.",
        )

    from adcopilot.infrastructure.demo.seeder import (
        DEMO_BUSINESSES,
        resolve_owner_user_id,
        seed_demo_data,
    )

    end_date = date.fromisoformat(body.end_date) if body.end_date else None
    businesses = DEMO_BUSINESSES[: body.accounts] if body.accounts else DEMO_BUSINESSES

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            # Owner = explicit email, else the calling admin themselves.
            if body.owner_email:
                owner_id = await resolve_owner_user_id(session, owner_email=body.owner_email)
                if owner_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"No user found with email {body.owner_email!r}",
                    )
            else:
                owner_id = uuid.UUID(current_user)

            counts = await seed_demo_data(
                session,
                businesses=businesses,
                days=body.days,
                end_date=end_date,
                reset=body.reset,
                owner_user_id=owner_id,
            )
    finally:
        await engine.dispose()

    logger.info(
        "demo_seed_completed",
        owner_user_id=str(owner_id),
        total_rows=sum(counts.values()),
    )
    return SeedDemoResponse(
        owner_user_id=str(owner_id),
        owner_email=body.owner_email,
        total_rows=sum(counts.values()),
        counts=counts,
    )
