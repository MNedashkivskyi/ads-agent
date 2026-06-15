"""Resolve a campaign's CIE context (account, vertical, language, service).

Resolves context for an *existing* campaign from the account it belongs to,
with optional request-body overrides. Verifies the account belongs to the
requesting user. Shared by the keyword and creative flows.

Greenfield campaign creation was retired in the optimization pivot (Phase 1),
so this resolver no longer reads a launch brief (T2.1). ``account_id`` is now
required, the vertical comes from the account's classified vertical (or an
override), and the service/language come from request overrides (or defaults).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.campaign_intelligence.shared.vertical import Vertical
from adcopilot.domain.entities import AccountId
from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
    SqlGoogleAdsAccountRepository,
)


class CampaignNotFound(LookupError):
    pass


class CampaignForbidden(PermissionError):
    pass


@dataclass(frozen=True)
class CampaignContext:
    account_id: str
    customer_id: str
    vertical: str
    language: str
    service: str


async def resolve_campaign_context(
    session: AsyncSession,
    *,
    campaign_id: str,
    user_id: str,
    account_id: str | None = None,
    vertical: str | None = None,
    language: str | None = None,
    service: str | None = None,
) -> CampaignContext:
    """Resolve CIE context for an existing campaign from its account.

    ``account_id`` is required (the launch-brief fallback was removed in the
    optimization pivot). ``vertical`` defaults to the account's classified
    vertical, ``language`` to Polish, and ``service`` to the supplied override
    (empty when none) — callers can pass a richer description derived from
    website intelligence when available.
    """
    if account_id is None:
        raise CampaignNotFound("account_id is required")

    account = await SqlGoogleAdsAccountRepository(session).get(AccountId(account_id))
    if account is None:
        raise CampaignNotFound("Account not found")
    if str(account.user_id) != user_id:
        raise CampaignForbidden("Account does not belong to user")

    raw_vertical = vertical or account.vertical
    return CampaignContext(
        account_id=account_id,
        customer_id=account.customer_id,
        vertical=Vertical.from_raw(raw_vertical).value.value,
        language=language or "pl",
        service=service or "",
    )
