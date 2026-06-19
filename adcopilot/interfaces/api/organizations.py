"""Organizations / team-seats API (Phase 3 / T3.4).

Lets a Business owner invite teammates into their organization and manage
members, with the seat count enforced by plan. Gated behind the ``team_seats``
capability (Business). Account-access sharing across an org is staged
separately (see migration 0078 / T6.1); this surface manages membership.
"""

from __future__ import annotations

import secrets
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from adcopilot.application.entitlements import Capability, max_seats
from adcopilot.config import Settings, get_settings
from adcopilot.domain.entities import PlanTier, UserId
from adcopilot.domain.organization import MembershipRole
from adcopilot.interfaces.api.auth_middleware import CurrentUser
from adcopilot.interfaces.api.deps import require_capability, require_phase5_enabled

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["organizations"])


class MemberResponse(BaseModel):
    user_id: str
    role: str
    created_at: str


class InviteRequest(BaseModel):
    email: str
    role: str = "MEMBER"

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip()
        if "@" not in v or "." not in v.split("@")[-1] or len(v) < 5:
            raise ValueError("Invalid email address")
        return v.lower()


class InviteResponse(BaseModel):
    invitation_id: str
    email: str
    role: str
    token: str  # returned so the owner can share the invite link


class AcceptResponse(BaseModel):
    organization_id: str
    role: str


async def _plan_for(session, user_id: str) -> PlanTier:  # noqa: ANN001
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

    user = await SqlUserRepository(session).get_by_id(UserId(user_id))
    return user.plan if user is not None else PlanTier.STARTER


@router.get("/{user_id}/organization/members", response_model=list[MemberResponse])
async def list_members(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    _cap: Annotated[None, Depends(require_capability(Capability.TEAM_SEATS))] = None,
    _p5: Annotated[None, Depends(require_phase5_enabled)] = None,
) -> list[MemberResponse]:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.organization_repository import (
        SqlOrganizationRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlOrganizationRepository(session)
            org = await repo.ensure_personal_org(user_id)
            members = await repo.list_members(org.id)
    finally:
        await engine.dispose()

    return [
        MemberResponse(user_id=m.user_id, role=m.role.value, created_at=m.created_at.isoformat())
        for m in members
    ]


@router.post("/{user_id}/organization/invitations", response_model=InviteResponse)
async def invite_member(
    user_id: str,
    body: InviteRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    _cap: Annotated[None, Depends(require_capability(Capability.TEAM_SEATS))] = None,
    _p5: Annotated[None, Depends(require_phase5_enabled)] = None,
) -> InviteResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.organization_repository import (
        SqlOrganizationRepository,
    )

    token = secrets.token_urlsafe(24)
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlOrganizationRepository(session)
            org = await repo.ensure_personal_org(user_id)
            plan = await _plan_for(session, user_id)

            used = await repo.count_members(org.id) + await repo.count_pending_invitations(org.id)
            if used >= max_seats(plan):
                raise HTTPException(
                    status_code=402,
                    detail=(
                        f"Osiągnięto limit miejsc dla planu {plan.value} "
                        f"(maks. {max_seats(plan)}). Zaktualizuj plan, aby dodać więcej osób."
                    ),
                )

            invitation = await repo.create_invitation(
                org.id, str(body.email), MembershipRole.parse(body.role), token
            )
    finally:
        await engine.dispose()

    logger.info("organization.invited", user_id=user_id, email=str(body.email))
    return InviteResponse(
        invitation_id=invitation.id,
        email=invitation.email,
        role=invitation.role.value,
        token=invitation.token,
    )


@router.post("/organizations/invitations/{token}/accept", response_model=AcceptResponse)
async def accept_invitation(
    token: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    _p5: Annotated[None, Depends(require_phase5_enabled)] = None,
) -> AcceptResponse:
    """Accept an invitation (the authenticated user joins the org)."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.organization_repository import (
        SqlOrganizationRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlOrganizationRepository(session)
            invitation = await repo.get_invitation_by_token(token)
            if invitation is None or not invitation.is_pending:
                raise HTTPException(status_code=404, detail="Zaproszenie nie istnieje lub wygasło")
            existing = await repo.get_membership(invitation.organization_id, current_user)
            if existing is None:
                await repo.add_member(invitation.organization_id, current_user, invitation.role)
            await repo.mark_invitation_accepted(token)
            org_id = invitation.organization_id
            role = invitation.role.value
    finally:
        await engine.dispose()

    logger.info("organization.invitation_accepted", user_id=current_user, org_id=org_id)
    return AcceptResponse(organization_id=org_id, role=role)


@router.delete("/{user_id}/organization/members/{member_user_id}")
async def remove_member(
    user_id: str,
    member_user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    _cap: Annotated[None, Depends(require_capability(Capability.TEAM_SEATS))] = None,
    _p5: Annotated[None, Depends(require_phase5_enabled)] = None,
) -> dict[str, str]:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.organization_repository import (
        SqlOrganizationRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlOrganizationRepository(session)
            org = await repo.ensure_personal_org(user_id)
            removed = await repo.remove_member(org.id, member_user_id)
    finally:
        await engine.dispose()

    if not removed:
        raise HTTPException(
            status_code=404, detail="Nie znaleziono członka lub nie można usunąć właściciela"
        )
    return {"status": "removed"}


# Allowed roles for clients building UIs.
ALLOWED_ROLES = tuple(r.value for r in MembershipRole)
