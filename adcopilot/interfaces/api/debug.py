"""Debug / diagnostics endpoints.

These are always mounted but intentionally cheap and side-effect-free so
they can safely stay in production — used to verify observability plumbing
end-to-end without deploying a special build.
"""

from __future__ import annotations

import os

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from adcopilot.config import get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"])


class SentryDebugError(RuntimeError):
    """Deliberate error raised by :func:`trigger_sentry` to verify wiring."""


class WebhookStatusResponse(BaseModel):
    registered_url: str | None
    registered_has_pending_update_count: int | None
    effective_base_url: str | None
    action: str


@router.post("/telegram-webhook/register")
async def register_telegram_webhook(request: Request) -> WebhookStatusResponse:
    """Re-register the Telegram webhook without redeploying.

    Useful when TELEGRAM_WEBHOOK_URL was just set or when the webhook was
    lost due to Telegram flood-control. Idempotent — safe to call repeatedly.
    """
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN not configured")

    from adcopilot.infrastructure.telegram.bot import register_webhook, resolve_webhook_secret

    base = settings.TELEGRAM_WEBHOOK_URL or (
        f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}"
        if os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        else None
    )
    if not base:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot determine webhook URL. Set TELEGRAM_WEBHOOK_URL="
                "https://<your-api-service>.up.railway.app in Railway variables."
            ),
        )

    webhook_url = base.rstrip("/") + "/telegram/webhook"
    secret = resolve_webhook_secret(settings)

    tg_app = getattr(request.app.state, "telegram_app", None)
    if tg_app is None:
        raise HTTPException(status_code=503, detail="Telegram bot not initialised")

    try:
        await register_webhook(tg_app.bot, webhook_url, secret)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Webhook registration failed: {exc}") from exc

    logger.info("telegram webhook re-registered via debug endpoint", url=webhook_url)
    return WebhookStatusResponse(
        registered_url=webhook_url,
        registered_has_pending_update_count=None,
        effective_base_url=base,
        action="registered",
    )


@router.get("/telegram-webhook/status")
async def telegram_webhook_status(request: Request) -> WebhookStatusResponse:
    """Return current Telegram webhook info (calls getWebhookInfo)."""
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN not configured")

    tg_app = getattr(request.app.state, "telegram_app", None)
    if tg_app is None:
        raise HTTPException(status_code=503, detail="Telegram bot not initialised")

    info = await tg_app.bot.get_webhook_info()
    base = settings.TELEGRAM_WEBHOOK_URL or (
        f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}"
        if os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        else None
    )
    return WebhookStatusResponse(
        registered_url=info.url or None,
        registered_has_pending_update_count=info.pending_update_count,
        effective_base_url=base,
        action="status",
    )


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
        "TELEGRAM_BOT_TOKEN": settings.TELEGRAM_BOT_TOKEN,
        "TELEGRAM_WEBHOOK_URL": settings.TELEGRAM_WEBHOOK_URL,
        "DATABASE_URL": settings.DATABASE_URL,
        "REDIS_URL": settings.REDIS_URL,
    }

    set_vars: dict[str, bool] = {k: bool(v) for k, v in required.items()}
    missing = [k for k, v in set_vars.items() if not v]

    warnings: list[str] = []
    if settings.SECRET_KEY == "change-me-in-production":
        warnings.append("SECRET_KEY is using the insecure default — set a random value in Railway")
    if settings.TOKEN_ENCRYPTION_KEY == "change-me-in-production-32-bytes":
        warnings.append("TOKEN_ENCRYPTION_KEY is using the insecure default — set a random 32-byte value")
    if settings.OAUTH_REDIRECT_URI and "localhost" in settings.OAUTH_REDIRECT_URI:
        warnings.append(
            f"OAUTH_REDIRECT_URI is set to '{settings.OAUTH_REDIRECT_URI}' which contains 'localhost' — "
            "this will not work in production. Set it to your Railway API public URL, e.g. "
            "https://<api-service>.up.railway.app/oauth/google/callback"
        )
    if not os.environ.get("RAILWAY_PUBLIC_DOMAIN") and not settings.TELEGRAM_WEBHOOK_URL:
        warnings.append(
            "Neither TELEGRAM_WEBHOOK_URL nor RAILWAY_PUBLIC_DOMAIN is available — "
            "Telegram webhook cannot be registered automatically"
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
