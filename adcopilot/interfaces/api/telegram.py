"""Telegram-related FastAPI routes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from telegram import Update

from adcopilot.config import Settings, get_settings
from adcopilot.infrastructure.telegram.bot import resolve_webhook_secret

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["telegram"])

LINK_TOKEN_EXPIRY_HOURS = 24
_LINK_TOKEN_SIG_BYTES = 10  # truncated HMAC-SHA256
_LINK_TOKEN_PAYLOAD_BYTES = 20  # 16-byte UUID + 4-byte expiry


def _make_link_token(user_id: str, secret_key: str) -> str:
    """Build a compact signed token suitable for Telegram's ``?start=`` parameter.

    Telegram's Bot API restricts the start payload to ``[A-Za-z0-9_-]{1,64}`` —
    which rules out JWTs (they contain ``.`` separators and easily exceed 64
    chars). This packs the user UUID + expiry into 20 bytes, signs it with a
    truncated HMAC-SHA256, and base64url-encodes the 30-byte result into a
    40-char token that is fully within Telegram's allowed charset.
    """
    uid_bytes = uuid.UUID(user_id).bytes  # 16 bytes
    exp_ts = int(time.time()) + LINK_TOKEN_EXPIRY_HOURS * 3600
    exp_bytes = struct.pack(">I", exp_ts)  # 4 bytes
    payload = uid_bytes + exp_bytes
    sig = hmac.new(
        secret_key.encode("utf-8"), payload, hashlib.sha256
    ).digest()[:_LINK_TOKEN_SIG_BYTES]
    token = base64.urlsafe_b64encode(payload + sig).decode("ascii").rstrip("=")
    return token


def _verify_link_token(token: str, secret_key: str) -> str | None:
    """Returns user_id or None if invalid/expired."""
    try:
        # Re-pad for base64 decoding (urlsafe_b64encode without padding emits
        # a multiple-of-4 string here anyway, but be defensive).
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, TypeError):
        return None

    if len(raw) != _LINK_TOKEN_PAYLOAD_BYTES + _LINK_TOKEN_SIG_BYTES:
        return None

    payload, sig = raw[:_LINK_TOKEN_PAYLOAD_BYTES], raw[_LINK_TOKEN_PAYLOAD_BYTES:]
    expected_sig = hmac.new(
        secret_key.encode("utf-8"), payload, hashlib.sha256
    ).digest()[:_LINK_TOKEN_SIG_BYTES]
    if not hmac.compare_digest(sig, expected_sig):
        return None

    (exp_ts,) = struct.unpack(">I", payload[16:20])
    if exp_ts < int(time.time()):
        return None

    try:
        user_id = str(uuid.UUID(bytes=payload[:16]))
    except ValueError:
        return None
    return user_id

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
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Generate a Telegram deep-link URL for the user to click and link their account."""
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")

    token = _make_link_token(user_id, settings.SECRET_KEY)
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
