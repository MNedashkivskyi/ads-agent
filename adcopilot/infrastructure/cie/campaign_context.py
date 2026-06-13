"""Resolve a campaign's CIE context (account, vertical, language, service).

Pulls defaults from the launch brief when ``campaign_id`` is a brief id, falling
back to request overrides and the account's classified vertical. Verifies the
account belongs to the requesting user. Shared by the keyword and creative flows.
"""

from __future__ import annotations

import uuid
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


async def _try_get_brief(session: AsyncSession, campaign_id: str, user_id: str):  # noqa: ANN202
    try:
        uuid.UUID(campaign_id)
    except ValueError:
        return None
    from adcopilot.domain.launch.entities import CampaignBriefId
    from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
        SqlCampaignBriefRepository,
    )

    brief = await SqlCampaignBriefRepository(session).get(CampaignBriefId(campaign_id))
    if brief is not None and str(brief.user_id) == user_id:
        return brief
    return None


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
    brief = await _try_get_brief(session, campaign_id, user_id)
    resolved_account = account_id or (str(brief.account_id) if brief else None)
    if resolved_account is None:
        raise CampaignNotFound("account_id is required when the campaign has no launch brief")

    account = await SqlGoogleAdsAccountRepository(session).get(AccountId(resolved_account))
    if account is None:
        raise CampaignNotFound("Account not found")
    if str(account.user_id) != user_id:
        raise CampaignForbidden("Account does not belong to user")

    raw_vertical = vertical or (brief.vertical if brief else None) or account.vertical
    return CampaignContext(
        account_id=resolved_account,
        customer_id=account.customer_id,
        vertical=Vertical.from_raw(raw_vertical).value.value,
        language=language or (brief.language if brief else None) or "pl",
        service=service or (brief.business_description if brief else "") or "",
    )
