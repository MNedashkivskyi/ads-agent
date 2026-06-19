"""Repository for agency prospects (Phase 5C)."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.agency import Prospect, ProspectStatus
from adcopilot.infrastructure.db.models import ProspectModel


def prospect_to_domain(m: ProspectModel) -> Prospect:
    return Prospect(
        id=str(m.id),
        organization_id=str(m.organization_id),
        customer_id=m.customer_id,
        name=m.name,
        status=ProspectStatus(m.status),
        mcc_customer_id=m.mcc_customer_id,
        audit_session_id=str(m.audit_session_id) if m.audit_session_id else None,
        report_id=str(m.report_id) if m.report_id else None,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlProspectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        organization_id: str,
        customer_id: str,
        name: str = "",
        mcc_customer_id: str | None = None,
    ) -> Prospect:
        """Create a prospect, or return the existing one for (org, customer_id)."""
        existing = (
            await self._session.execute(
                select(ProspectModel).where(
                    ProspectModel.organization_id == uuid.UUID(organization_id),
                    ProspectModel.customer_id == customer_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if name and existing.name != name:
                existing.name = name
                await self._session.flush()
            return prospect_to_domain(existing)
        m = ProspectModel(
            id=uuid.uuid4(),
            organization_id=uuid.UUID(organization_id),
            customer_id=customer_id,
            name=name,
            status=ProspectStatus.NEW.value,
            mcc_customer_id=mcc_customer_id,
        )
        self._session.add(m)
        await self._session.flush()
        return prospect_to_domain(m)

    async def get(self, prospect_id: str) -> Prospect | None:
        m = await self._session.get(ProspectModel, uuid.UUID(prospect_id))
        return prospect_to_domain(m) if m else None

    async def list_for_orgs(self, organization_ids: list[str]) -> list[Prospect]:
        if not organization_ids:
            return []
        rows = (
            await self._session.execute(
                select(ProspectModel)
                .where(ProspectModel.organization_id.in_([uuid.UUID(o) for o in organization_ids]))
                .order_by(ProspectModel.created_at.desc())
            )
        ).scalars()
        return [prospect_to_domain(m) for m in rows]

    async def set_status(self, prospect_id: str, status: ProspectStatus) -> bool:
        result = await self._session.execute(
            update(ProspectModel)
            .where(ProspectModel.id == uuid.UUID(prospect_id))
            .values(status=status.value)
        )
        return result.rowcount > 0

    async def set_audit(
        self, prospect_id: str, *, audit_session_id: str | None, report_id: str | None
    ) -> None:
        """Attach the latest audit + report to a prospect and mark it AUDITED."""
        await self._session.execute(
            update(ProspectModel)
            .where(ProspectModel.id == uuid.UUID(prospect_id))
            .values(
                audit_session_id=uuid.UUID(audit_session_id) if audit_session_id else None,
                report_id=uuid.UUID(report_id) if report_id else None,
                status=ProspectStatus.AUDITED.value,
            )
        )
