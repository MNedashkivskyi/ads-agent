"""Integration test: org-membership account access (Phase 5B-2).

Owner and org members can access an account; a stranger cannot. list_for_user
returns accounts across the orgs a user belongs to. Requires TEST_DATABASE_URL.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import AccountId, GoogleAdsAccount, UserId
from adcopilot.domain.organization import MembershipRole
from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
    SqlGoogleAdsAccountRepository,
)
from adcopilot.infrastructure.db.repositories.organization_repository import (
    SqlOrganizationRepository,
)
from adcopilot.interfaces.api.account_access import can_access_account


async def _make_account(db_session: AsyncSession, owner: str, org_id: str) -> GoogleAdsAccount:
    return await SqlGoogleAdsAccountRepository(db_session).save(
        GoogleAdsAccount(
            id=AccountId(str(uuid.uuid4())),
            user_id=UserId(owner),
            customer_id=str(uuid.uuid4().int)[:10],
            descriptive_name="Org Acc",
            currency="PLN",
            timezone="Europe/Warsaw",
            is_manager=False,
            write_enabled=True,
            connected_at=datetime(2026, 1, 1, tzinfo=UTC),
            organization_id=org_id,
        )
    )


@pytest.mark.integration
async def test_owner_and_member_can_access_stranger_cannot(db_session: AsyncSession) -> None:
    org_repo = SqlOrganizationRepository(db_session)
    owner, member, stranger = (str(uuid.uuid4()) for _ in range(3))
    org = await org_repo.ensure_personal_org(owner)
    await org_repo.add_member(str(org.id), member, MembershipRole.MEMBER)
    acc = await _make_account(db_session, owner, str(org.id))

    assert await can_access_account(db_session, acc, owner) is True
    assert await can_access_account(db_session, acc, member) is True
    assert await can_access_account(db_session, acc, stranger) is False


@pytest.mark.integration
async def test_list_for_user_includes_org_accounts(db_session: AsyncSession) -> None:
    org_repo = SqlOrganizationRepository(db_session)
    acc_repo = SqlGoogleAdsAccountRepository(db_session)
    owner, member = str(uuid.uuid4()), str(uuid.uuid4())
    org = await org_repo.ensure_personal_org(owner)
    await org_repo.add_member(str(org.id), member, MembershipRole.MEMBER)
    acc = await _make_account(db_session, owner, str(org.id))

    member_accounts = await acc_repo.list_for_user(UserId(member))
    assert any(a.id == acc.id for a in member_accounts)
    owner_accounts = await acc_repo.list_for_user(UserId(owner))
    assert any(a.id == acc.id for a in owner_accounts)
