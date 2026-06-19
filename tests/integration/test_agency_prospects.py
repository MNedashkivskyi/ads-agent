"""Integration test: agency prospects repo + audit agency_org_id (Phase 5C-1)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.agency import ProspectStatus
from adcopilot.infrastructure.db.repositories.agency_repository import SqlProspectRepository
from adcopilot.infrastructure.db.repositories.audit_repository import SqlAuditSessionRepository


@pytest.mark.integration
async def test_prospect_upsert_list_and_status(db_session: AsyncSession) -> None:
    org_id = str(uuid.uuid4())
    repo = SqlProspectRepository(db_session)

    p = await repo.upsert(
        organization_id=org_id, customer_id="1112223334", name="Acme", mcc_customer_id="9990001112"
    )
    # upsert is idempotent on (org, customer_id).
    again = await repo.upsert(organization_id=org_id, customer_id="1112223334", name="Acme")
    assert again.id == p.id

    listed = await repo.list_for_orgs([org_id])
    assert any(x.id == p.id for x in listed)
    assert listed[0].mcc_customer_id == "9990001112"

    assert await repo.set_status(p.id, ProspectStatus.CONTACTED) is True
    fetched = await repo.get(p.id)
    assert fetched is not None
    assert fetched.status is ProspectStatus.CONTACTED


@pytest.mark.integration
async def test_audit_session_agency_org_id_round_trips(db_session: AsyncSession) -> None:
    sessions = SqlAuditSessionRepository(db_session)
    org_id = str(uuid.uuid4())
    created = await sessions.create(google_customer_id="1234567890", agency_org_id=org_id)
    fetched = await sessions.get(created.id)
    assert fetched is not None
    assert fetched.agency_org_id == org_id
