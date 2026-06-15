"""Repository for organizations / memberships / invitations (Phase 3 / T3.4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.organization import (
    Membership,
    MembershipRole,
    Organization,
    OrganizationInvitation,
)
from adcopilot.infrastructure.db.models import (
    MembershipModel,
    OrganizationInvitationModel,
    OrganizationModel,
)


def _org(m: OrganizationModel) -> Organization:
    return Organization(
        id=str(m.id),
        name=m.name,
        owner_user_id=m.owner_user_id,
        is_personal=m.is_personal,
        created_at=m.created_at,
    )


def _member(m: MembershipModel) -> Membership:
    return Membership(
        id=str(m.id),
        organization_id=str(m.organization_id),
        user_id=m.user_id,
        role=MembershipRole.parse(m.role),
        created_at=m.created_at,
    )


def _invite(m: OrganizationInvitationModel) -> OrganizationInvitation:
    return OrganizationInvitation(
        id=str(m.id),
        organization_id=str(m.organization_id),
        email=m.email,
        role=MembershipRole.parse(m.role),
        token=m.token,
        accepted_at=m.accepted_at,
        created_at=m.created_at,
    )


class SqlOrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_personal_org_for_owner(self, user_id: str) -> Organization | None:
        m = (
            await self._session.execute(
                select(OrganizationModel).where(
                    OrganizationModel.owner_user_id == user_id,
                    OrganizationModel.is_personal.is_(True),
                )
            )
        ).scalar_one_or_none()
        return _org(m) if m else None

    async def ensure_personal_org(self, user_id: str) -> Organization:
        existing = await self.get_personal_org_for_owner(user_id)
        if existing is not None:
            return existing
        org = OrganizationModel(
            id=uuid.uuid4(), name="", owner_user_id=user_id, is_personal=True
        )
        self._session.add(org)
        await self._session.flush()
        self._session.add(
            MembershipModel(
                id=uuid.uuid4(),
                organization_id=org.id,
                user_id=user_id,
                role=MembershipRole.OWNER.value,
            )
        )
        await self._session.flush()
        return _org(org)

    async def list_members(self, organization_id: str) -> list[Membership]:
        rows = (
            await self._session.execute(
                select(MembershipModel)
                .where(MembershipModel.organization_id == uuid.UUID(organization_id))
                .order_by(MembershipModel.created_at.asc())
            )
        ).scalars()
        return [_member(m) for m in rows]

    async def count_members(self, organization_id: str) -> int:
        return int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(MembershipModel)
                    .where(MembershipModel.organization_id == uuid.UUID(organization_id))
                )
            ).scalar_one()
        )

    async def count_pending_invitations(self, organization_id: str) -> int:
        return int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(OrganizationInvitationModel)
                    .where(
                        OrganizationInvitationModel.organization_id == uuid.UUID(organization_id),
                        OrganizationInvitationModel.accepted_at.is_(None),
                    )
                )
            ).scalar_one()
        )

    async def get_membership(self, organization_id: str, user_id: str) -> Membership | None:
        m = (
            await self._session.execute(
                select(MembershipModel).where(
                    MembershipModel.organization_id == uuid.UUID(organization_id),
                    MembershipModel.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        return _member(m) if m else None

    async def add_member(
        self, organization_id: str, user_id: str, role: MembershipRole
    ) -> None:
        self._session.add(
            MembershipModel(
                id=uuid.uuid4(),
                organization_id=uuid.UUID(organization_id),
                user_id=user_id,
                role=role.value,
            )
        )
        await self._session.flush()

    async def remove_member(self, organization_id: str, user_id: str) -> bool:
        result = await self._session.execute(
            delete(MembershipModel).where(
                MembershipModel.organization_id == uuid.UUID(organization_id),
                MembershipModel.user_id == user_id,
                MembershipModel.role != MembershipRole.OWNER.value,
            )
        )
        return result.rowcount > 0

    async def create_invitation(
        self, organization_id: str, email: str, role: MembershipRole, token: str
    ) -> OrganizationInvitation:
        m = OrganizationInvitationModel(
            id=uuid.uuid4(),
            organization_id=uuid.UUID(organization_id),
            email=email.lower(),
            role=role.value,
            token=token,
        )
        self._session.add(m)
        await self._session.flush()
        return _invite(m)

    async def get_invitation_by_token(self, token: str) -> OrganizationInvitation | None:
        m = (
            await self._session.execute(
                select(OrganizationInvitationModel).where(
                    OrganizationInvitationModel.token == token
                )
            )
        ).scalar_one_or_none()
        return _invite(m) if m else None

    async def mark_invitation_accepted(self, token: str) -> None:
        await self._session.execute(
            update(OrganizationInvitationModel)
            .where(OrganizationInvitationModel.token == token)
            .values(accepted_at=datetime.now(UTC))
        )

    async def list_org_ids_for_member(self, user_id: str) -> list[str]:
        rows = (
            await self._session.execute(
                select(MembershipModel.organization_id).where(
                    MembershipModel.user_id == user_id
                )
            )
        ).scalars()
        return [str(r) for r in rows]
