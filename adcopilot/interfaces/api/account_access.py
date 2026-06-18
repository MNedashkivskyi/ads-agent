"""Shared account authorization (Phase 5B — org-owned accounts).

A user may access a Google Ads account if they own it (legacy/personal) OR are a
member of its owning organization. Centralised so every account-scoped endpoint
applies the same rule. Fails closed: no org and not the owner → no access.
"""

from __future__ import annotations

from typing import Any

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
