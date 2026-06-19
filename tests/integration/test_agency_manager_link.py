"""Integration test: agency MCC link stores the refresh token encrypted (Phase 5C-2)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.agency import AgencyManagerLink
from adcopilot.infrastructure.db.models import AgencyManagerLinkModel
from adcopilot.infrastructure.db.repositories.agency_repository import (
    SqlAgencyManagerLinkRepository,
)

_KEY = "test-encryption-key-32-bytes-ok!"


@pytest.mark.integration
async def test_mcc_link_round_trips_and_encrypts_token(db_session: AsyncSession) -> None:
    repo = SqlAgencyManagerLinkRepository(db_session, _KEY)
    org_id = str(uuid.uuid4())

    await repo.save(
        AgencyManagerLink(
            organization_id=org_id, mcc_customer_id="9990001112", refresh_token="secret-token"
        )
    )

    got = await repo.get(org_id)
    assert got is not None
    assert got.mcc_customer_id == "9990001112"
    assert got.refresh_token == "secret-token"  # decrypted on read

    # The token is NOT stored in plaintext.
    row = (
        await db_session.execute(
            select(AgencyManagerLinkModel).where(
                AgencyManagerLinkModel.organization_id == uuid.UUID(org_id)
            )
        )
    ).scalar_one()
    assert row.refresh_token_encrypted != "secret-token"


@pytest.mark.integration
async def test_mcc_link_save_replaces_existing(db_session: AsyncSession) -> None:
    repo = SqlAgencyManagerLinkRepository(db_session, _KEY)
    org_id = str(uuid.uuid4())
    await repo.save(
        AgencyManagerLink(organization_id=org_id, mcc_customer_id="111", refresh_token="a")
    )
    await repo.save(
        AgencyManagerLink(organization_id=org_id, mcc_customer_id="222", refresh_token="b")
    )

    got = await repo.get(org_id)
    assert got is not None
    assert got.mcc_customer_id == "222"
    assert got.refresh_token == "b"
