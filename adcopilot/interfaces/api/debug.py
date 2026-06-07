"""Debug / diagnostics endpoints.

DEV-ONLY: this router is registered only when not running in production
(see main.create_app). The raw-token Google Ads endpoints were removed
entirely — they accepted attacker-supplied refresh tokens. What remains
(env-check, sentry) is for local diagnostics.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter
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
