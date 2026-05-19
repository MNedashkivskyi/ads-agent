"""Search terms API endpoints — GET list and POST block."""

from __future__ import annotations

from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from adcopilot.application.use_cases.detect_search_term_waste import detect_search_term_waste
from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["search-terms"])

_PLN_DIVISOR = 1_000_000  # micros → PLN


class SearchTermResponse(BaseModel):
    search_term: str
    account_id: str
    account_name: str = ""
    campaign_name: str
    cost_pln: float
    clicks: int
    impressions: int
    conversions: float
    is_wasteful: bool = False


class BlockSearchTermRequest(BaseModel):
    term: str
    account_id: str
    scope: Literal["all_campaigns", "campaign_id"]
    campaign_id: int | None = None


class BlockSearchTermResponse(BaseModel):
    term: str
    campaigns_affected: int
    message: str


@router.get("/{user_id}/search-terms", response_model=list[SearchTermResponse])
async def list_search_terms(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=20, ge=1, le=100),
    account_id: str | None = Query(default=None),
) -> list[SearchTermResponse]:
    """Return top search terms by cost. Use account_id=all to aggregate across all accounts."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter

    engine = create_async_engine(settings.DATABASE_URL)
    multi_account = account_id == "all"
    try:
        async with AsyncSession(engine) as session, session.begin():
            account_repo = SqlGoogleAdsAccountRepository(session)
            credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)

            if account_id and not multi_account:
                account = await account_repo.get(AccountId(account_id))
                if account is None or str(account.user_id) != user_id:
                    raise HTTPException(status_code=404, detail="Account not found")
                target_accounts = [account]
            else:
                target_accounts = await account_repo.list_for_user(UserId(user_id))
                if not target_accounts:
                    raise HTTPException(status_code=404, detail="No Google Ads accounts found")
                if not multi_account:
                    target_accounts = target_accounts[:1]

            google_ads = GoogleAdsQueriesAdapter(settings)
            results: list[SearchTermResponse] = []

            for acct in target_accounts:
                credentials = await credentials_repo.get(AccountId(acct.id))
                if credentials is None:
                    continue

                snapshots = await google_ads.list_recent_search_terms(
                    credentials.refresh_token,
                    acct.customer_id,
                    days=days,
                    limit=limit,
                )

                waste_recs = detect_search_term_waste(acct.id, snapshots)
                waste_terms = {r.evidence["search_term"] for r in waste_recs}

                for s in snapshots:
                    results.append(
                        SearchTermResponse(
                            search_term=s.search_term,
                            account_id=str(acct.id),
                            account_name=getattr(acct, "name", str(acct.id)),
                            campaign_name=s.campaign_name,
                            cost_pln=round(s.cost_micros / _PLN_DIVISOR, 2),
                            clicks=s.clicks,
                            impressions=s.impressions,
                            conversions=s.conversions,
                            is_wasteful=s.search_term in waste_terms,
                        )
                    )

            if not results and not multi_account:
                raise HTTPException(status_code=422, detail="Account not connected")
    finally:
        await engine.dispose()

    results.sort(key=lambda r: r.cost_pln, reverse=True)
    return results[:limit]


@router.post("/{user_id}/search-terms/block", response_model=BlockSearchTermResponse)
async def block_search_term(
    user_id: str,
    body: BlockSearchTermRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> BlockSearchTermResponse:
    """Add a negative keyword for the given search term across campaigns."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.domain.audit_log import AuditLog, AuditLogId
    from adcopilot.domain.entities import AccountId
    from adcopilot.domain.recommendation import RecommendationId
    from adcopilot.infrastructure.db.repositories.audit_log_repository import SqlAuditLogRepository
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.db.repositories.snapshot_repository import SqlSnapshotRepository
    from adcopilot.infrastructure.google_ads.mutations_adapter import GoogleAdsMutationsAdapter

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account_repo = SqlGoogleAdsAccountRepository(session)
            credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)
            snapshot_repo = SqlSnapshotRepository(session)
            audit_repo = SqlAuditLogRepository(session)

            account = await account_repo.get(AccountId(body.account_id))
            if account is None or str(account.user_id) != user_id:
                raise HTTPException(status_code=404, detail="Account not found")
            if not account.write_enabled:
                raise HTTPException(status_code=403, detail="Account write not enabled")

            credentials = await credentials_repo.get(AccountId(body.account_id))
            if credentials is None:
                raise HTTPException(status_code=422, detail="Account not connected")

            mutations = GoogleAdsMutationsAdapter(settings)

            if body.scope == "campaign_id":
                if body.campaign_id is None:
                    raise HTTPException(status_code=422, detail="campaign_id required for scope=campaign_id")
                campaign_ids = [body.campaign_id]
            else:
                # all_campaigns — fetch from latest snapshot
                latest_date = await snapshot_repo.get_latest_snapshot_date(AccountId(body.account_id))
                if latest_date is None:
                    raise HTTPException(status_code=422, detail="No snapshot data available")
                campaigns = await snapshot_repo.get_campaigns_by_date(
                    AccountId(body.account_id), latest_date
                )
                campaign_ids = list({c.campaign_id for c in campaigns if c.status == "ENABLED"})
                if not campaign_ids:
                    raise HTTPException(status_code=422, detail="No enabled campaigns found")

            for cid in campaign_ids:
                await mutations.add_campaign_negative_keyword(
                    refresh_token=credentials.refresh_token,
                    customer_id=account.customer_id,
                    campaign_id=cid,
                    keyword_text=body.term,
                    match_type="EXACT",
                )

            audit = AuditLog(
                id=AuditLogId(_new_uuid()),
                recommendation_id=RecommendationId(_new_uuid()),
                account_id=AccountId(body.account_id),
                kind="BLOCK_SEARCH_TERM",
                action="EXECUTE",
                payload={
                    "term": body.term,
                    "scope": body.scope,
                    "campaign_ids": campaign_ids,
                    "user_id": user_id,
                },
                created_at=datetime.now(UTC),
            )
            await audit_repo.save(audit)
    finally:
        await engine.dispose()

    n = len(campaign_ids)
    message = f"Zablokowano: '{body.term}'. Dodano jako negatyw do {n} kampanii."

    try:
        from adcopilot.infrastructure.notifications.web_notifier_adapter import SqlWebNotifier

        async with AsyncSession(create_async_engine(settings.DATABASE_URL)) as notif_session, notif_session.begin():
            notifier = SqlWebNotifier(notif_session)
            await notifier.send_alert(user_id=user_id, title="Zablokowano frazę", body=message)
    except Exception:
        logger.warning("search_term_block.notification_failed", user_id=user_id, term=body.term)

    return BlockSearchTermResponse(term=body.term, campaigns_affected=n, message=message)


def _new_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
