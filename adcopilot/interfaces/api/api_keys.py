"""Customer API access (Phase 3 / T3.5).

Two surfaces:

1. **Key management** (authenticated app users, gated behind ``api_access`` —
   Business): create / list / revoke keys. The plaintext secret is returned
   exactly once at creation.
2. **Public read API** (``/api/public/*``): authenticated by an ``X-API-Key``
   header, per-key rate-limited, read-only. Exposes performance and
   recommendations for accounts the key's owner controls. The owner must still
   hold the ``api_access`` capability for the key to work.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from adcopilot.application.entitlements import Capability, has_capability
from adcopilot.config import Settings, get_settings
from adcopilot.domain.api_key import generate_api_key, hash_key
from adcopilot.domain.entities import PlanTier
from adcopilot.interfaces.api.auth_middleware import CurrentUser
from adcopilot.interfaces.api.deps import require_capability
from adcopilot.rate_limit import limiter

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["api-keys"])

_PUBLIC_RATE_LIMIT = "120/minute"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CreateApiKeyRequest(BaseModel):
    name: str = Field(default="", max_length=120)


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    display_prefix: str
    created_at: str
    revoked_at: str | None
    last_used_at: str | None


class CreatedApiKeyResponse(ApiKeyResponse):
    # Plaintext secret — shown exactly once.
    secret: str


# ---------------------------------------------------------------------------
# Key management (gated behind api_access)
# ---------------------------------------------------------------------------


@router.post("/{user_id}/api-keys", response_model=CreatedApiKeyResponse)
async def create_api_key(
    user_id: str,
    body: CreateApiKeyRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    _cap: Annotated[None, Depends(require_capability(Capability.API_ACCESS))] = None,
) -> CreatedApiKeyResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.api_key_repository import SqlApiKeyRepository

    generated = generate_api_key()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            created = await SqlApiKeyRepository(session).create(
                user_id=user_id,
                name=body.name,
                display_prefix=generated.display_prefix,
                key_hash=generated.key_hash,
            )
    finally:
        await engine.dispose()

    logger.info("api_key.created", user_id=user_id, key_id=created.id)
    return CreatedApiKeyResponse(
        id=created.id,
        name=created.name,
        display_prefix=created.display_prefix,
        created_at=created.created_at.isoformat(),
        revoked_at=None,
        last_used_at=None,
        secret=generated.plaintext,
    )


@router.get("/{user_id}/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    _cap: Annotated[None, Depends(require_capability(Capability.API_ACCESS))] = None,
) -> list[ApiKeyResponse]:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.api_key_repository import SqlApiKeyRepository

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            keys = await SqlApiKeyRepository(session).list_for_user(user_id)
    finally:
        await engine.dispose()

    return [
        ApiKeyResponse(
            id=k.id,
            name=k.name,
            display_prefix=k.display_prefix,
            created_at=k.created_at.isoformat(),
            revoked_at=k.revoked_at.isoformat() if k.revoked_at else None,
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
        )
        for k in keys
    ]


@router.delete("/{user_id}/api-keys/{key_id}")
async def revoke_api_key(
    user_id: str,
    key_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    _cap: Annotated[None, Depends(require_capability(Capability.API_ACCESS))] = None,
) -> dict[str, str]:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.api_key_repository import SqlApiKeyRepository

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            ok = await SqlApiKeyRepository(session).revoke(user_id, key_id)
    finally:
        await engine.dispose()

    if not ok:
        raise HTTPException(status_code=404, detail="Klucz API nie został znaleziony")
    return {"status": "revoked"}


# ---------------------------------------------------------------------------
# Public read API (X-API-Key auth)
# ---------------------------------------------------------------------------


async def resolve_api_key_user(
    settings: Settings,
    x_api_key: str | None,
) -> str:
    """Resolve an ``X-API-Key`` header to the owning user id.

    Raises 401 when the key is missing/invalid/revoked, and 403 when the owner
    is no longer entitled to ``api_access``.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.api_key_repository import SqlApiKeyRepository
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            key = await SqlApiKeyRepository(session).get_active_by_hash(hash_key(x_api_key))
            if key is None:
                raise HTTPException(status_code=401, detail="Invalid API key")
            from adcopilot.domain.entities import UserId

            user = await SqlUserRepository(session).get_by_id(UserId(key.user_id))
            plan = user.plan if user is not None else PlanTier.STARTER
            if not has_capability(plan, Capability.API_ACCESS):
                raise HTTPException(status_code=403, detail="API access not available on your plan")
            await SqlApiKeyRepository(session).touch_last_used(key.id)
            return key.user_id
    finally:
        await engine.dispose()


async def _verify_account_owner(session, account_id: str, user_id: str) -> str:  # noqa: ANN001
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    account = await SqlGoogleAdsAccountRepository(session).get(AccountId(account_id))
    if account is None or str(account.user_id) != user_id:
        raise HTTPException(status_code=404, detail="Account not found")
    return account.customer_id


@router.get("/public/recommendations")
@limiter.limit(_PUBLIC_RATE_LIMIT, key_func=lambda r: r.headers.get("X-API-Key", "anon"))
async def public_recommendations(
    request: Request,
    response: Response,
    account_id: Annotated[str, Query()],
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    """Read-only: PENDING recommendations for an account the key owner controls."""
    user_id = await resolve_api_key_user(settings, x_api_key)

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            await _verify_account_owner(session, account_id, user_id)
            recs = await SqlRecommendationRepository(session).list_pending(AccountId(account_id))
    finally:
        await engine.dispose()

    return {
        "account_id": account_id,
        "recommendations": [
            {
                "id": str(r.id),
                "kind": r.kind.value,
                "severity": r.severity.value,
                "estimated_monthly_savings_micros": r.estimated_monthly_savings_micros,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recs
        ],
    }


@router.get("/public/performance")
@limiter.limit(_PUBLIC_RATE_LIMIT, key_func=lambda r: r.headers.get("X-API-Key", "anon"))
async def public_performance(
    request: Request,
    response: Response,
    account_id: Annotated[str, Query()],
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    """Read-only: latest performance summary for an account the key owner controls."""
    user_id = await resolve_api_key_user(settings, x_api_key)

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.services.account_context_builder import AccountContextBuilder
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.audit_log_repository import SqlAuditLogRepository
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )
    from adcopilot.infrastructure.db.repositories.snapshot_repository import SqlSnapshotRepository

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            await _verify_account_owner(session, account_id, user_id)
            builder = AccountContextBuilder(
                SqlSnapshotRepository(session),
                SqlRecommendationRepository(session),
                SqlAuditLogRepository(session),
            )
            ctx = await builder.build(AccountId(account_id))
    finally:
        await engine.dispose()

    return {
        "account_id": account_id,
        "snapshot_date": ctx.get("snapshot_date"),
        "summary": ctx.get("summary"),
        "week_over_week_deltas": ctx.get("week_over_week_deltas"),
    }
