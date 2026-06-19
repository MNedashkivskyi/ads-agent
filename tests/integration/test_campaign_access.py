"""Integration test: campaign/account access hardening (pre-5B gaps closed)."""

import uuid
from datetime import UTC, date, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import AccountId, GoogleAdsAccount, UserId
from adcopilot.domain.organization import MembershipRole
from adcopilot.infrastructure.db.models import CampaignSnapshotModel
from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
    SqlGoogleAdsAccountRepository,
)
from adcopilot.infrastructure.db.repositories.organization_repository import (
    SqlOrganizationRepository,
)
from adcopilot.interfaces.api.account_access import (
    require_account_access,
    resolve_campaign_account_id,
)


async def _seed_account_in_org(
    db_session: AsyncSession, owner: str, member: str | None = None
) -> str:
    org_repo = SqlOrganizationRepository(db_session)
    org = await org_repo.ensure_personal_org(owner)
    if member:
        await org_repo.add_member(str(org.id), member, MembershipRole.MEMBER)
    account_id = AccountId(str(uuid.uuid4()))
    await SqlGoogleAdsAccountRepository(db_session).save(
        GoogleAdsAccount(
            id=account_id,
            user_id=UserId(owner),
            customer_id=str(uuid.uuid4().int)[:10],
            descriptive_name="X",
            currency="PLN",
            timezone="Europe/Warsaw",
            is_manager=False,
            write_enabled=True,
            connected_at=datetime(2026, 1, 1, tzinfo=UTC),
            organization_id=str(org.id),
        )
    )
    return str(account_id)


@pytest.mark.integration
async def test_require_account_access_allows_member_denies_stranger(
    db_session: AsyncSession,
) -> None:
    owner, member, stranger = (str(uuid.uuid4()) for _ in range(3))
    account_id = await _seed_account_in_org(db_session, owner, member)

    assert (await require_account_access(db_session, account_id, owner)).id == account_id
    assert (await require_account_access(db_session, account_id, member)).id == account_id
    with pytest.raises(HTTPException) as exc:
        await require_account_access(db_session, account_id, stranger)
    assert exc.value.status_code == 404


@pytest.mark.integration
async def test_resolve_campaign_account_id(db_session: AsyncSession) -> None:
    owner = str(uuid.uuid4())
    account_id = await _seed_account_in_org(db_session, owner)
    db_session.add(
        CampaignSnapshotModel(
            id=uuid.uuid4(),
            account_id=uuid.UUID(account_id),
            campaign_id=4242,
            snapshot_date=date(2026, 5, 1),
        )
    )
    await db_session.flush()

    assert await resolve_campaign_account_id(db_session, "4242") == account_id
    assert await resolve_campaign_account_id(db_session, "99999") is None
    assert await resolve_campaign_account_id(db_session, "not-an-int") is None
