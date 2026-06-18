"""Integration test: GoogleAdsAccount.organization_id round-trips (Phase 5B foundation)."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import AccountId, GoogleAdsAccount, UserId
from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
    SqlGoogleAdsAccountRepository,
)


def _account(org_id: str | None) -> GoogleAdsAccount:
    return GoogleAdsAccount(
        id=AccountId(str(uuid.uuid4())),
        user_id=UserId(str(uuid.uuid4())),
        customer_id=str(uuid.uuid4().int)[:10],
        descriptive_name="Org Test",
        currency="PLN",
        timezone="Europe/Warsaw",
        is_manager=False,
        write_enabled=True,
        connected_at=datetime(2026, 1, 1, tzinfo=UTC),
        organization_id=org_id,
    )


@pytest.mark.integration
async def test_account_persists_organization_id(db_session: AsyncSession) -> None:
    repo = SqlGoogleAdsAccountRepository(db_session)
    org_id = str(uuid.uuid4())

    acc = _account(org_id)
    saved = await repo.save(acc)
    assert saved.organization_id == org_id

    fetched = await repo.get(acc.id)
    assert fetched is not None
    assert fetched.organization_id == org_id


@pytest.mark.integration
async def test_account_organization_id_optional(db_session: AsyncSession) -> None:
    # Legacy/unbackfilled accounts have no org yet — must still round-trip as None.
    repo = SqlGoogleAdsAccountRepository(db_session)
    fetched = await repo.get((await repo.save(_account(None))).id)
    assert fetched is not None
    assert fetched.organization_id is None
