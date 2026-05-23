"""Debug / diagnostics endpoints.

These are always mounted but intentionally cheap and side-effect-free so
they can safely stay in production — used to verify observability plumbing
end-to-end without deploying a special build.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adcopilot.config import get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"])


class SentryDebugError(RuntimeError):
    """Deliberate error raised by :func:`trigger_sentry` to verify wiring."""


class EnvCheckResponse(BaseModel):
    ok: bool
    missing: list[str]
    set_vars: dict[str, bool]
    warnings: list[str]


@router.get("/env-check")
async def env_check() -> EnvCheckResponse:
    """Check that all required env vars are set.

    Returns a JSON summary of which vars are present and which are missing.
    Use this endpoint from Railway to diagnose missing configuration before
    debugging OAuth or Telegram issues.
    """
    settings = get_settings()

    required: dict[str, str | None] = {
        "GOOGLE_ADS_DEVELOPER_TOKEN": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
        "GOOGLE_ADS_CLIENT_ID": settings.GOOGLE_ADS_CLIENT_ID,
        "GOOGLE_ADS_CLIENT_SECRET": settings.GOOGLE_ADS_CLIENT_SECRET,
        "OAUTH_REDIRECT_URI": settings.OAUTH_REDIRECT_URI,
        "APP_URL": settings.APP_URL,
        "DATABASE_URL": settings.DATABASE_URL,
        "REDIS_URL": settings.REDIS_URL,
    }

    set_vars: dict[str, bool] = {k: bool(v) for k, v in required.items()}
    missing = [k for k, v in set_vars.items() if not v]

    warnings: list[str] = []
    if settings.SECRET_KEY == "change-me-in-production":
        warnings.append("SECRET_KEY is using the insecure default — set a random value in Railway")
    if settings.TOKEN_ENCRYPTION_KEY == "change-me-in-production-32-bytes":
        warnings.append(
            "TOKEN_ENCRYPTION_KEY is using the insecure default — set a random 32-byte value"
        )
    if settings.OAUTH_REDIRECT_URI and "localhost" in settings.OAUTH_REDIRECT_URI:
        warnings.append(
            f"OAUTH_REDIRECT_URI is set to '{settings.OAUTH_REDIRECT_URI}' which contains 'localhost' — "
            "this will not work in production. Set it to your Railway API public URL, e.g. "
            "https://<api-service>.up.railway.app/oauth/google/callback"
        )

    return EnvCheckResponse(
        ok=len(missing) == 0,
        missing=missing,
        set_vars=set_vars,
        warnings=warnings,
    )


class GoogleAdsTestResponse(BaseModel):
    ok: bool
    resource_names: list[str]
    customer_ids: list[str]
    error: str | None
    error_type: str | None


@router.get("/google-ads-test")
async def google_ads_test(refresh_token: str) -> GoogleAdsTestResponse:
    """Test Google Ads API connectivity with a given refresh token.

    Pass ?refresh_token=<token> to verify that the developer token and OAuth
    credentials work together. Returns the raw resource names returned by
    list_accessible_customers, plus any error details.

    Use this to diagnose why the OAuth callback returns error=google_ads_api_error.
    """
    import traceback

    settings = get_settings()
    from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter

    client = GoogleAdsClientAdapter(settings)
    try:
        resource_names = await client.list_accessible_customers(refresh_token)
        customer_ids = [rn.split("/")[-1] for rn in resource_names]
        return GoogleAdsTestResponse(
            ok=True,
            resource_names=resource_names,
            customer_ids=customer_ids,
            error=None,
            error_type=None,
        )
    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("google-ads-test failed", error=str(exc), traceback=tb)
        return GoogleAdsTestResponse(
            ok=False,
            resource_names=[],
            customer_ids=[],
            error=str(exc),
            error_type=type(exc).__name__,
        )


class CreateTestAccountRequest(BaseModel):
    mcc_customer_id: str
    refresh_token: str
    account_name: str = "AdsWise Test Account"
    currency_code: str = "PLN"
    time_zone: str = "Europe/Warsaw"


class CreateTestAccountResponse(BaseModel):
    ok: bool
    customer_id: str | None
    resource_name: str | None
    error: str | None
    error_type: str | None
    next_step: str | None


@router.post("/create-test-account")
async def create_test_account(body: CreateTestAccountRequest) -> CreateTestAccountResponse:
    """Create a test Google Ads client account under an MCC.

    Use this when you have a test developer token and need a test account
    to verify the OAuth linking flow without providing billing info.

    Requires a refresh token for a Google account with manager access to the MCC.
    Get one from https://developers.google.com/oauthplayground using your
    GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET with scope:
    https://www.googleapis.com/auth/adwords
    """
    import traceback

    settings = get_settings()

    if not settings.GOOGLE_ADS_DEVELOPER_TOKEN:
        raise HTTPException(status_code=503, detail="GOOGLE_ADS_DEVELOPER_TOKEN not configured")

    mcc_id = body.mcc_customer_id.replace("-", "").strip()

    try:
        import google.ads.googleads.client as gads

        config = {
            "developer_token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
            "client_id": settings.GOOGLE_ADS_CLIENT_ID or "",
            "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET or "",
            "refresh_token": body.refresh_token,
            "login_customer_id": mcc_id,
            "use_proto_plus": True,
        }
        client = gads.GoogleAdsClient.load_from_dict(config)

        customer_service = client.get_service("CustomerService")
        customer = client.get_type("Customer")
        customer.descriptive_name = body.account_name
        customer.currency_code = body.currency_code
        customer.time_zone = body.time_zone
        customer.test_account = True

        response = customer_service.create_customer_client(
            customer_id=mcc_id,
            customer_client=customer,
        )

        new_customer_id = response.resource_name.split("/")[-1]
        logger.info(
            "test google ads account created",
            mcc_customer_id=mcc_id,
            new_customer_id=new_customer_id,
        )
        return CreateTestAccountResponse(
            ok=True,
            customer_id=new_customer_id,
            resource_name=response.resource_name,
            error=None,
            error_type=None,
            next_step=(
                f"Test account {new_customer_id} created successfully. "
                "Now go to adswise.xyz/app/connect and complete the Google OAuth flow "
                "using the same Google account that manages the MCC. "
                "The test account will appear in 'Połączone konta'."
            ),
        )
    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("failed to create test google ads account", error=str(exc), traceback=tb)
        return CreateTestAccountResponse(
            ok=False,
            customer_id=None,
            resource_name=None,
            error=str(exc),
            error_type=type(exc).__name__,
            next_step=None,
        )


@router.get("/sentry")
async def trigger_sentry() -> None:
    """Raise a ``SentryDebugError`` so the Sentry integration can be verified.

    Used during onboarding to confirm the DSN is reachable and the
    before_send hook does not drop events.  Returns nothing on success —
    the caller is expected to see a 500 in their browser and a matching
    event in the Sentry dashboard within ~10 seconds.
    """
    logger.warning("debug sentry endpoint hit — raising deliberate error")
    raise SentryDebugError("Deliberate test error from /debug/sentry — Sentry integration check.")
