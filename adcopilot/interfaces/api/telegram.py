"""Telegram-related FastAPI routes."""

from __future__ import annotations

import hmac
import uuid
from typing import Annotated

import redis as redis_sync
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from telegram import Update

from adcopilot.config import Settings, get_settings
from adcopilot.infrastructure.telegram.bot import resolve_webhook_secret
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["telegram"])

# Telegram's ?start= payload allows only [A-Za-z0-9_-], max 64 chars.
# A UUID4 hex string (32 lowercase hex chars) fits within that limit perfectly.
_TG_LINK_TOKEN_PREFIX = "tg-link:"
_TG_LINK_TOKEN_TTL_SECONDS = 24 * 3600


def _make_link_token(user_id: str, redis_client: redis_sync.Redis) -> str:  # type: ignore[type-arg]
    """Generate a short opaque token, store user_id in Redis, and return the token."""
    token = uuid.uuid4().hex  # 32 lowercase hex chars — valid Telegram start payload
    redis_client.set(
        _TG_LINK_TOKEN_PREFIX + token,
        user_id,
        ex=_TG_LINK_TOKEN_TTL_SECONDS,
    )
    return token


def _verify_link_token(token: str, redis_client: redis_sync.Redis) -> str | None:  # type: ignore[type-arg]
    """Look up the token in Redis, consume it (single-use), and return user_id or None."""
    key = _TG_LINK_TOKEN_PREFIX + token
    value = redis_client.get(key)
    if value is None:
        return None
    redis_client.delete(key)
    return value.decode() if isinstance(value, bytes) else str(value)


def _get_redis_client(settings: Annotated[Settings, Depends(get_settings)]) -> redis_sync.Redis:  # type: ignore[type-arg]
    return redis_sync.Redis.from_url(settings.REDIS_URL)


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Receive a Telegram webhook update and forward it to the bot Application.

    The bot Application is initialised once at FastAPI startup (see
    ``main.py`` lifespan) and stored in ``request.app.state.telegram_app``.
    This endpoint does *not* build or teardown the Application — it simply
    calls ``process_update`` on the already-running instance.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")

    # Verify the secret token Telegram echoes on every webhook request.
    # Prefers TELEGRAM_WEBHOOK_SECRET when set, otherwise the HMAC-derived
    # value.  ``hmac.compare_digest`` is constant-time to prevent timing
    # attacks.  A missing or mismatched header returns 403 immediately.
    expected_secret = resolve_webhook_secret(settings)
    if x_telegram_bot_api_secret_token is None or not hmac.compare_digest(
        x_telegram_bot_api_secret_token, expected_secret
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook secret token")

    tg_app = getattr(request.app.state, "telegram_app", None)
    if tg_app is None:
        raise HTTPException(status_code=503, detail="Telegram bot not initialised")

    body = await request.json()
    update = Update.de_json(body, tg_app.bot)
    await tg_app.process_update(update)

    return {"ok": "true"}


@router.post("/api/users/{user_id}/telegram-link")
async def generate_telegram_link(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Generate a Telegram deep-link URL for the user to click and link their account."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")

    redis_client = redis_sync.Redis.from_url(settings.REDIS_URL)
    try:
        token = _make_link_token(user_id, redis_client)
    finally:
        redis_client.close()

    bot_name = await _get_bot_username(settings.TELEGRAM_BOT_TOKEN)
    deep_link_url = f"https://t.me/{bot_name}?start={token}"
    return {"deep_link_url": deep_link_url}


async def _get_bot_username(bot_token: str) -> str:
    """Fetch the bot's username via getMe."""
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
    if resp.status_code != 200:
        raise HTTPException(status_code=503, detail="Failed to fetch bot info")
    data = resp.json()
    username: str = data["result"]["username"]
    return username
