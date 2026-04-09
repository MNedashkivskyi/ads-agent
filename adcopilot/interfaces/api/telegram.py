"""Telegram-related FastAPI routes."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from jose import JWTError, jwt
from telegram import Update

from adcopilot.config import Settings, get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["telegram"])

LINK_JWT_ALGORITHM = "HS256"
LINK_JWT_EXPIRY_HOURS = 24


def _make_link_jwt(user_id: str, secret_key: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(UTC) + timedelta(hours=LINK_JWT_EXPIRY_HOURS),
        "jti": str(uuid.uuid4()),
        "type": "tg_link",
    }
    token: str = jwt.encode(payload, secret_key, algorithm=LINK_JWT_ALGORITHM)
    return token


def _verify_link_jwt(token: str, secret_key: str) -> str | None:
    """Returns user_id or None if invalid/expired."""
    try:
        payload = jwt.decode(token, secret_key, algorithms=[LINK_JWT_ALGORITHM])
        if payload.get("type") != "tg_link":
            return None
        user_id: str = payload["sub"]
        return user_id
    except JWTError:
        return None


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Receives Telegram webhook updates and forwards them to the bot Application."""
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")

    # Verify the secret token header
    expected_secret = _compute_webhook_secret(settings.TELEGRAM_BOT_TOKEN)
    if x_telegram_bot_api_secret_token != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret token")

    body = await request.json()
    update = Update.de_json(body, None)

    from adcopilot.infrastructure.telegram.bot import build_telegram_app

    app = build_telegram_app(settings)
    await app.initialize()
    await app.process_update(update)
    await app.shutdown()

    return {"ok": "true"}


@router.post("/api/users/{user_id}/telegram-link")
async def generate_telegram_link(
    user_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Generate a Telegram deep-link URL for the user to click and link their account."""
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")

    token = _make_link_jwt(user_id, settings.SECRET_KEY)
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


def _compute_webhook_secret(bot_token: str) -> str:
    """Derive a webhook secret from the bot token (HMAC-SHA256 of token with key 'WebhookSecret')."""
    return hmac.new(b"WebhookSecret", bot_token.encode(), hashlib.sha256).hexdigest()
