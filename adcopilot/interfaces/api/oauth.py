"""Google OAuth2 flow for Google Ads API access."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

import httpx
import redis as redis_sync
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import Settings, get_settings
from adcopilot.domain.entities import AccountId, GoogleAdsAccount, OAuthCredentials, UserId
from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
    SqlGoogleAdsAccountRepository,
)
from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
    SqlOAuthCredentialsRepository,
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
    """
    return redis_sync.Redis.from_url(settings.REDIS_URL)


from collections.abc import AsyncGenerator  # noqa: E402


async def _get_db_session(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(settings.DATABASE_URL)
    async with AsyncSession(engine) as session:
        yield session
    await engine.dispose()


@router.get("/google/start")
async def oauth_google_start(
    user_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Returns the Google OAuth redirect URL. The caller should redirect the user there."""
    if not settings.GOOGLE_ADS_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    state = issue_state_jwt(user_id, settings.SECRET_KEY)
    callback_url = "http://localhost:8000/oauth/google/callback"  # configurable in prod

    params = {
        "client_id": settings.GOOGLE_ADS_CLIENT_ID,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": GOOGLE_ADS_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return {"auth_url": auth_url}


@router.get("/google/callback")
async def oauth_google_callback(
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(_get_db_session)],
    redis_client: Annotated[redis_sync.Redis, Depends(_get_redis_client)],
) -> dict[str, object]:
    """Exchanges code for tokens, stores credentials, returns linked customer IDs."""
    if not settings.GOOGLE_ADS_CLIENT_ID or not settings.GOOGLE_ADS_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    # Validate state JWT — prevents CSRF and, via Redis single-use marker,
    # also prevents replay of a captured state value.
    try:
        user_id = consume_state_jwt(state, settings.SECRET_KEY, redis_client=redis_client)
    except StateAlreadyUsedError as exc:
        logger.warning("oauth state replay attempted")
        raise HTTPException(status_code=400, detail="OAuth state already used") from exc
    except StateTokenInvalidError as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state") from exc

    user_repo = SqlUserRepository(session)
    user = await user_repo.get_by_id(UserId(user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    callback_url = "http://localhost:8000/oauth/google/callback"

    # Exchange authorization code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_ADS_CLIENT_ID,
                "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
                "redirect_uri": callback_url,
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

    # List accessible Google Ads customer IDs
    from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter

    ads_client = GoogleAdsClientAdapter(settings)
    try:
        customer_ids = await ads_client.list_accessible_customers(refresh_token)
    except Exception as exc:
        logger.warning("failed to list google ads customers", error=str(exc))
        customer_ids = []

    acc_repo = SqlGoogleAdsAccountRepository(session)
    creds_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)

    # Enforce per-plan account limits
    _PLAN_ACCOUNT_LIMITS: dict[str, int] = {
        "starter": 1,
        "growth": 3,
        "pro": 10,
    }
    existing_accounts = await acc_repo.list_for_user(UserId(user_id))
    account_limit = _PLAN_ACCOUNT_LIMITS.get(user.plan.value, 1)
    if len(existing_accounts) >= account_limit:
        raise HTTPException(
            status_code=402,
            detail=f"Account limit reached for {user.plan.value} plan ({account_limit} max). Upgrade to add more accounts.",
        )

    linked_ids: list[str] = []
    for customer_id in customer_ids:
        account_id = AccountId(str(uuid.uuid5(uuid.NAMESPACE_URL, f"{user_id}/{customer_id}")))
        account = GoogleAdsAccount(
            id=account_id,
            user_id=UserId(user_id),
            customer_id=customer_id,
            descriptive_name="",
            currency="",
            timezone="",
            is_manager=False,
            write_enabled=False,
            connected_at=datetime.now(UTC),
        )
        await acc_repo.save(account)

        creds = OAuthCredentials(
            account_id=account_id,
            refresh_token=refresh_token,
            access_token=access_token,
            expires_at=expires_at,
        )
        await creds_repo.save(creds)
        linked_ids.append(customer_id)

    await session.commit()
    logger.info("google oauth complete", user_id=user_id, accounts=len(linked_ids))

    return {"user_id": user_id, "linked_customer_ids": linked_ids}
