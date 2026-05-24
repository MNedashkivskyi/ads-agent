"""Google OAuth2 flow for Google Ads API access."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

import httpx
import redis as redis_sync
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import Settings, get_settings
from adcopilot.domain.entities import UserId
from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
    SqlGoogleAdsAccountRepository,
)
from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository
from adcopilot.security import (
    StateAlreadyUsedError,
    StateTokenInvalidError,
    consume_state_jwt,
    issue_state_jwt,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"


def _get_redis_client(settings: Annotated[Settings, Depends(get_settings)]) -> redis_sync.Redis:
    """FastAPI dependency — returns a sync Redis client for state replay storage.

    We use the sync client intentionally: the ``consume_state_jwt`` helper
    performs a single ``SET NX`` call, and building the client per request
    (connection pooled under the hood) is simpler than managing an async
    pool in the single-consumer OAuth callback hot path.

    We set short socket timeouts so a Redis outage fails fast (5 s)
    instead of blocking the event loop for the Linux TCP default (~120 s).
    """
    return redis_sync.Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


from collections.abc import AsyncGenerator  # noqa: E402


async def _get_db_session(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(settings.DATABASE_URL)
    async with AsyncSession(engine) as session:
        yield session
    await engine.dispose()


_PLAN_ACCOUNT_LIMITS: dict[str, int] = {"starter": 1, "growth": 3, "pro": 10}


@router.get("/google/start")
async def oauth_google_start(
    user_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(_get_db_session)],
) -> RedirectResponse:
    """Redirects the browser directly to Google's OAuth consent screen.

    Enforces per-plan account limits *before* redirecting to Google so
    users who have already reached their quota get an immediate error
    redirect instead of completing the consent flow only to be rejected
    in the callback.
    """
    if not settings.GOOGLE_ADS_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    # Server-side plan limit check — never trust the frontend's check alone.
    user_repo = SqlUserRepository(session)
    user = await user_repo.ensure_exists(UserId(user_id))
    await session.commit()

    acc_repo = SqlGoogleAdsAccountRepository(session)
    existing_accounts = await acc_repo.list_for_user(UserId(user_id))
    account_limit = _PLAN_ACCOUNT_LIMITS.get(user.plan.value, 1)

    if len(existing_accounts) >= account_limit:
        logger.warning(
            "oauth.start.quota_exceeded",
            user_id=user_id,
            plan=user.plan.value,
            current=len(existing_accounts),
            limit=account_limit,
        )
        if settings.APP_URL:
            return RedirectResponse(
                url=f"{settings.APP_URL.rstrip('/')}/app/google-ads-connect?error=quota_exceeded",
                status_code=302,
            )
        raise HTTPException(
            status_code=402,
            detail=f"Account limit reached for {user.plan.value} plan ({account_limit} max). Upgrade to add more accounts.",
        )

    state = issue_state_jwt(user_id, settings.SECRET_KEY)

    params = {
        "client_id": settings.GOOGLE_ADS_CLIENT_ID,
        "redirect_uri": settings.OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_ADS_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/google/callback", response_model=None)
async def oauth_google_callback(
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(_get_db_session)],
    redis_client: Annotated[redis_sync.Redis, Depends(_get_redis_client)],
) -> RedirectResponse | dict[str, object]:
    """Exchange code for tokens, queue account-linking as a Celery task, redirect.

    The Google Ads API calls (list_accessible_customers, get_customer_info) use
    synchronous gRPC under the hood.  Running them inside the FastAPI event loop
    — even via asyncio.to_thread — risks starving the event loop when the gRPC
    C extension holds the GIL.  We therefore do *no* Google Ads API calls here:
    the refresh token is stored encrypted in Redis and a Celery worker (separate
    process, separate GIL) picks it up to finish account linking.
    """
    import asyncio
    import base64
    import hashlib
    import json

    from cryptography.fernet import Fernet

    if not settings.GOOGLE_ADS_CLIENT_ID or not settings.GOOGLE_ADS_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    # Validate state JWT — prevents CSRF and replay attacks.
    # consume_state_jwt uses a *synchronous* Redis SET NX call.  We run it
    # in a thread so a slow/unreachable Redis doesn't block the event loop.
    try:
        user_id = await asyncio.wait_for(
            asyncio.to_thread(
                consume_state_jwt, state, settings.SECRET_KEY, redis_client=redis_client
            ),
            timeout=10,
        )
    except StateAlreadyUsedError as exc:
        logger.warning("oauth state replay attempted")
        raise HTTPException(status_code=400, detail="OAuth state already used") from exc
    except StateTokenInvalidError as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state") from exc
    except (redis_sync.ConnectionError, redis_sync.TimeoutError, TimeoutError, OSError) as exc:
        logger.error("redis unavailable during oauth state validation", error=str(exc))
        raise HTTPException(
            status_code=503, detail="Service temporarily unavailable — please try again"
        ) from exc

    user_repo = SqlUserRepository(session)
    user = await user_repo.ensure_exists(UserId(user_id))
    await session.commit()

    # Exchange authorization code for tokens (fast httpx call, has 15 s timeout).
    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_ADS_CLIENT_ID,
                "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
                "redirect_uri": settings.OAUTH_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

    if token_resp.status_code != 200:
        logger.error("google token exchange failed", status=token_resp.status_code)
        raise HTTPException(status_code=400, detail="Failed to exchange OAuth code")

    token_data = token_resp.json()
    refresh_token: str = token_data.get("refresh_token", "")
    access_token: str | None = token_data.get("access_token")
    expires_in: int | None = token_data.get("expires_in")
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in) if expires_in else None

    if not refresh_token:
        raise HTTPException(status_code=400, detail="No refresh_token in Google response")

    # Enforce per-plan account limits *before* queuing the task so the user
    # gets an immediate error rather than a silent no-op from the worker.
    acc_repo = SqlGoogleAdsAccountRepository(session)
    existing_accounts = await acc_repo.list_for_user(UserId(user_id))
    account_limit = _PLAN_ACCOUNT_LIMITS.get(user.plan.value, 1)
    if len(existing_accounts) >= account_limit:
        raise HTTPException(
            status_code=402,
            detail=f"Account limit reached for {user.plan.value} plan ({account_limit} max). Upgrade to add more accounts.",
        )

    # Guard: developer token is required for every Google Ads API call.
    if not settings.GOOGLE_ADS_DEVELOPER_TOKEN:
        logger.error(
            "GOOGLE_ADS_DEVELOPER_TOKEN is not set — cannot call Google Ads API. "
            "Set this env var in Railway to enable Google Ads account linking."
        )
        if settings.APP_URL:
            return RedirectResponse(
                url=f"{settings.APP_URL.rstrip('/')}/app/google-ads-connect?connected=0&error=missing_developer_token",
                status_code=302,
            )
        raise HTTPException(
            status_code=503,
            detail="Google Ads API not configured: missing GOOGLE_ADS_DEVELOPER_TOKEN",
        )

    # Encrypt and store the refresh token in Redis.  The Celery task reads it,
    # calls the Google Ads API (in a separate worker process), and cleans up.
    fernet_key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.TOKEN_ENCRYPTION_KEY.encode()).digest()
    )
    fernet = Fernet(fernet_key)
    pending_payload = json.dumps(
        {
            "refresh_token": refresh_token,
            "access_token": access_token,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
    ).encode()
    enc_token = fernet.encrypt(pending_payload)
    pending_redis_key = f"oauth_pending:{user_id}"

    try:
        await asyncio.wait_for(
            asyncio.to_thread(redis_client.set, pending_redis_key, enc_token, ex=3600),
            timeout=10,
        )
    except (redis_sync.ConnectionError, redis_sync.TimeoutError, TimeoutError, OSError) as exc:
        logger.error("redis unavailable — cannot store pending token", error=str(exc))
        raise HTTPException(
            status_code=503, detail="Service temporarily unavailable — please try again"
        ) from exc

    # Dispatch the linking task to a Celery worker.
    from adcopilot.interfaces.worker.tasks import link_google_ads_accounts_task

    link_google_ads_accounts_task.delay(user_id)
    logger.info("google oauth code exchanged — account linking queued", user_id=user_id)

    # Redirect immediately.  The frontend shows a "pending" state; accounts
    # appear after the Celery worker finishes (usually within 10–30 seconds).
    if settings.APP_URL:
        base = settings.APP_URL.rstrip("/")
        return RedirectResponse(
            url=f"{base}/app/google-ads-connect?pending=1",
            status_code=302,
        )
    return {"user_id": user_id, "status": "pending"}


GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
GA4_TOKEN_URL = "https://oauth2.googleapis.com/token"


@router.get("/ga4/start")
async def oauth_ga4_start(
    user_id: str,
    account_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    """Redirect to Google OAuth consent for GA4 Data API (read-only)."""
    if not settings.GOOGLE_ADS_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    state = issue_state_jwt(f"{user_id}:{account_id}", settings.SECRET_KEY)
    params = {
        "client_id": settings.GOOGLE_ADS_CLIENT_ID,
        "redirect_uri": settings.GA4_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": GA4_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=302)


@router.get("/ga4/callback", response_model=None)
async def oauth_ga4_callback(
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    property_id: Annotated[str | None, Query()] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
    session: Annotated[AsyncSession, Depends(_get_db_session)] = None,
    redis_client: Annotated[redis_sync.Redis, Depends(_get_redis_client)] = None,
) -> dict:
    """Exchange GA4 code for tokens, store credentials."""
    if not settings.GOOGLE_ADS_CLIENT_ID or not settings.GOOGLE_ADS_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    import asyncio

    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(
                consume_state_jwt, state, settings.SECRET_KEY, redis_client=redis_client
            ),
            timeout=10,
        )
        user_id, account_id = payload.split(":", 1)
    except (StateAlreadyUsedError, StateTokenInvalidError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state") from exc
    except (redis_sync.ConnectionError, redis_sync.TimeoutError, TimeoutError, OSError) as exc:
        logger.error("redis unavailable during ga4 oauth state validation", error=str(exc))
        raise HTTPException(
            status_code=503, detail="Service temporarily unavailable — please try again"
        ) from exc

    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(
            GA4_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_ADS_CLIENT_ID,
                "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
                "redirect_uri": settings.GA4_OAUTH_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
    token_data = token_resp.json()
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="No refresh token returned")

    import base64
    import hashlib

    from cryptography.fernet import Fernet

    from adcopilot.infrastructure.db.models import GA4CredentialsModel

    key = base64.urlsafe_b64encode(hashlib.sha256(settings.TOKEN_ENCRYPTION_KEY.encode()).digest())
    fernet = Fernet(key)
    enc_refresh = fernet.encrypt(refresh_token.encode()).decode()
    pid = property_id or ""

    # Upsert into ga4_credentials
    from sqlalchemy import select

    result = await session.execute(
        select(GA4CredentialsModel).where(GA4CredentialsModel.account_id == uuid.UUID(account_id))
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.property_id = pid
        existing.refresh_token_enc = enc_refresh
    else:
        session.add(
            GA4CredentialsModel(
                account_id=uuid.UUID(account_id),
                property_id=pid,
                refresh_token_enc=enc_refresh,
            )
        )
    await session.commit()
    logger.info("ga4 oauth complete", user_id=user_id, account_id=account_id)

    if settings.APP_URL:
        return RedirectResponse(
            url=f"{settings.APP_URL.rstrip('/')}/app/audiences?ga4=connected", status_code=302
        )
    return {"status": "ok", "account_id": account_id}
