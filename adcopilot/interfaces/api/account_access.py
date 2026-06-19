"""Shared account authorization (Phase 5B — org-owned accounts).

A user may access a Google Ads account if they own it (legacy/personal) OR are a
member of its owning organization. Centralised so every account-scoped endpoint
applies the same rule. Fails closed: no org and not the owner → no access.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from adcopilot.domain.entities import GoogleAdsAccount
from adcopilot.infrastructure.db.repositories.organization_repository import (
    SqlOrganizationRepository,
)


async def can_access_account(session: Any, account: GoogleAdsAccount, user_id: str) -> bool:
    """True if ``user_id`` owns ``account`` or is a member of its organization."""
    if str(account.user_id) == user_id:
        return True
    if account.organization_id:
        membership = await SqlOrganizationRepository(session).get_membership(
            account.organization_id, user_id
        )
        return membership is not None
    return False


async def require_account_access(session: Any, account_id: str, user_id: str) -> GoogleAdsAccount:
    """Load the account and assert the caller can access it; 404 otherwise.

    For callers that already hold a DB session.
    """
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    account = await SqlGoogleAdsAccountRepository(session).get(AccountId(account_id))
    if account is None or not await can_access_account(session, account, user_id):
        raise HTTPException(status_code=404, detail="Konto nie zostało znalezione")
    return account


async def resolve_campaign_account_id(session: Any, campaign_id: str) -> str | None:
    """The account id a campaign belongs to, from its snapshot — None if unknown."""
    from sqlalchemy import select

    from adcopilot.infrastructure.db.models import CampaignSnapshotModel

    try:
        cid = int(campaign_id)
    except (TypeError, ValueError):
        return None
    row = (
        await session.execute(
            select(CampaignSnapshotModel.account_id)
            .where(CampaignSnapshotModel.campaign_id == cid)
            .limit(1)
        )
    ).first()
    return str(row[0]) if row else None


async def assert_campaign_access(settings: Any, campaign_id: str, user_id: str) -> None:
    """Resolve a campaign to its account and assert access — opens its own session.

    For campaign-keyed endpoints that don't hold a DB session. Fails CLOSED: an
    unknown campaign (no snapshot to resolve the account from) or no access → 404.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_id = await resolve_campaign_account_id(session, campaign_id)
            if account_id is None:
                raise HTTPException(status_code=404, detail="Kampania nie została znaleziona")
            await require_account_access(session, account_id, user_id)
    finally:
        await engine.dispose()
