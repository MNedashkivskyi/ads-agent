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
from adcopilot.domain.entities import AccountId, GoogleAdsAccount, OAuthCredentials, UserId
from adcopilot.domain.exceptions import GoogleAdsTokenNotApproved
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
) -> RedirectResponse:
    """Redirects the browser directly to Google's OAuth consent screen."""
    if not settings.GOOGLE_ADS_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

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

    # Exchange authorization code for tokens
    async with httpx.AsyncClient() as client:
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

    acc_repo = SqlGoogleAdsAccountRepository(session)
    creds_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)

    # Enforce per-plan account limits before calling the Google Ads API
    _PLAN_ACCOUNT_LIMITS: dict[str, int] = {
        "starter": 1,
        "growth": 3,
        "pro": 10,
    }
    existing_accounts = await acc_repo.list_for_user(UserId(user_id))
    account_limit = _PLAN_ACCOUNT_LIMITS.get(user.plan.value, 1)
    slots_remaining = account_limit - len(existing_accounts)
    if slots_remaining <= 0:
        raise HTTPException(
            status_code=402,
            detail=f"Account limit reached for {user.plan.value} plan ({account_limit} max). Upgrade to add more accounts.",
        )

    # List accessible Google Ads customer IDs.
    # list_accessible_customers returns resource names like "customers/1234567890".
    # Extract the plain numeric ID from each resource name.
    from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter

    # Guard: developer token is required for every Google Ads API call.
    if not settings.GOOGLE_ADS_DEVELOPER_TOKEN:
        logger.error(
            "GOOGLE_ADS_DEVELOPER_TOKEN is not set — cannot call Google Ads API. "
            "Set this env var in Railway to enable Google Ads account linking."
        )
        if settings.APP_URL:
            return RedirectResponse(
                url=f"{settings.APP_URL.rstrip('/')}/app?connected=0&error=missing_developer_token",
                status_code=302,
            )
        raise HTTPException(status_code=503, detail="Google Ads API not configured: missing GOOGLE_ADS_DEVELOPER_TOKEN")

    ads_client = GoogleAdsClientAdapter(settings)
    google_ads_api_error: str | None = None
    try:
        resource_names = await ads_client.list_accessible_customers(refresh_token)
        customer_ids = [rn.split("/")[-1] for rn in resource_names]
    except GoogleAdsTokenNotApproved as exc:
        logger.error(
            "google ads developer token not approved for production — "
            "apply for Standard Access at Google Ads → Admin → API Center",
            error=str(exc),
        )
        if settings.APP_URL:
            return RedirectResponse(
                url=f"{settings.APP_URL.rstrip('/')}/app?connected=0&error=token_not_approved",
                status_code=302,
            )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        import traceback

        logger.error(
            "failed to list google ads customers",
            error=str(exc),
            error_type=type(exc).__name__,
            traceback=traceback.format_exc(),
            developer_token_set=bool(settings.GOOGLE_ADS_DEVELOPER_TOKEN),
            client_id_set=bool(settings.GOOGLE_ADS_CLIENT_ID),
        )
        google_ads_api_error = f"{type(exc).__name__}: {exc}"
        customer_ids = []

    linked_ids: list[str] = []
    for customer_id in customer_ids[:slots_remaining]:
        account_id = AccountId(str(uuid.uuid5(uuid.NAMESPACE_URL, f"{user_id}/{customer_id}")))

        # Fetch real account details so the dashboard shows name/currency/timezone.
        descriptive_name = ""
        currency = ""
        timezone = ""
        is_manager = False
        try:
            info = await ads_client.get_customer_info(refresh_token, customer_id)
            descriptive_name = info.descriptive_name
            currency = info.currency
            timezone = info.timezone
            is_manager = info.is_manager
        except Exception as exc:
            logger.warning(
                "failed to fetch customer info — saving with defaults",
                customer_id=customer_id,
                error=str(exc),
            )

        account = GoogleAdsAccount(
            id=account_id,
            user_id=UserId(user_id),
            customer_id=customer_id,
            descriptive_name=descriptive_name,
            currency=currency,
            timezone=timezone,
            is_manager=is_manager,
            write_enabled=not is_manager,
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

    # Notify the user via Telegram if they have a linked chat.
    if user.telegram_chat_id and settings.TELEGRAM_BOT_TOKEN:
        try:
            from telegram import Bot

            if linked_ids:
                tg_msg = (
                    f"✅ Google Ads połączono pomyślnie!\n\n"
                    f"Połączono {len(linked_ids)} konto{'a' if len(linked_ids) > 1 else ''}.\n"
                    f"Przejdź do adswise.xyz/app, aby zobaczyć szczegóły i rekomendacje."
                )
            else:
                tg_msg = (
                    "⚠️ Autoryzacja Google zakończona, ale nie znaleziono żadnych kont Google Ads.\n\n"
                    "Upewnij się, że masz dostęp do konta Google Ads i spróbuj ponownie na adswise.xyz/app/connect."
                )
            async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
                await bot.send_message(chat_id=user.telegram_chat_id, text=tg_msg)
        except Exception:
            logger.warning(
                "failed to send google ads connected telegram notification",
                user_id=user_id,
            )

    # Redirect the browser back to the frontend dashboard.
    # APP_URL is the frontend origin (e.g. https://adswise.xyz).
    # Falls back to a generic success message if APP_URL is not configured.
    if settings.APP_URL:
        base = settings.APP_URL.rstrip("/")
        if google_ads_api_error and not linked_ids:
            # API call failed — show a distinct error message on the frontend
            # so the user knows it's a configuration issue, not "no accounts".
            redirect_url = f"{base}/app?connected=0&error=google_ads_api_error"
        else:
            redirect_url = f"{base}/app?connected={len(linked_ids)}"
        return RedirectResponse(url=redirect_url, status_code=302)
    return {"user_id": user_id, "linked_customer_ids": linked_ids}
