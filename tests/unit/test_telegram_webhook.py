"""Unit tests for the Telegram webhook endpoint and related helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adcopilot.infrastructure.telegram.bot import (
    compute_webhook_secret,
    resolve_webhook_secret,
)

_BOT_TOKEN = "123456:ABCDefgh_test_token"
_SECRET = compute_webhook_secret(_BOT_TOKEN)


# ---------------------------------------------------------------------------
# compute_webhook_secret
# ---------------------------------------------------------------------------


def test_compute_webhook_secret_is_deterministic() -> None:
    assert compute_webhook_secret(_BOT_TOKEN) == compute_webhook_secret(_BOT_TOKEN)


def test_compute_webhook_secret_differs_for_different_tokens() -> None:
    assert compute_webhook_secret(_BOT_TOKEN) != compute_webhook_secret("other_token")


def test_compute_webhook_secret_returns_hex_string() -> None:
    secret = compute_webhook_secret(_BOT_TOKEN)
    # SHA-256 hex digest is always 64 characters
    assert len(secret) == 64
    assert all(c in "0123456789abcdef" for c in secret)


# ---------------------------------------------------------------------------
# telegram_webhook endpoint
# ---------------------------------------------------------------------------


def _make_request(
    body: dict,
    app_state_tg_app: object | None,
    secret_header: str | None = _SECRET,
) -> MagicMock:
    """Build a minimal mock FastAPI Request."""
    request = MagicMock()
    request.json = AsyncMock(return_value=body)
    request.app = MagicMock()
    request.app.state = MagicMock(spec=[])  # empty state by default
    if app_state_tg_app is not None:
        request.app.state.telegram_app = app_state_tg_app
    return request


def _make_settings(
    bot_token: str | None = _BOT_TOKEN,
    webhook_secret: str | None = None,
) -> MagicMock:
    settings = MagicMock()
    settings.TELEGRAM_BOT_TOKEN = bot_token
    # Default to None so the HMAC-derived fallback is used in existing tests.
    settings.TELEGRAM_WEBHOOK_SECRET = webhook_secret
    return settings


@pytest.mark.asyncio
async def test_webhook_returns_ok_when_valid() -> None:
    from adcopilot.interfaces.api.telegram import telegram_webhook

    tg_app = MagicMock()
    tg_app.bot = MagicMock()
    tg_app.process_update = AsyncMock()

    request = _make_request(body={"update_id": 1}, app_state_tg_app=tg_app)

    with patch("adcopilot.interfaces.api.telegram.Update.de_json", return_value=MagicMock()):
        result = await telegram_webhook(
            request=request,
            settings=_make_settings(),
            x_telegram_bot_api_secret_token=_SECRET,
        )

    assert result == {"ok": "true"}
    tg_app.process_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_webhook_returns_403_for_wrong_secret() -> None:
    from fastapi import HTTPException

    from adcopilot.interfaces.api.telegram import telegram_webhook

    tg_app = MagicMock()
    request = _make_request(body={}, app_state_tg_app=tg_app)

    with pytest.raises(HTTPException) as exc_info:
        await telegram_webhook(
            request=request,
            settings=_make_settings(),
            x_telegram_bot_api_secret_token="wrong-secret",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_webhook_returns_403_when_no_secret_header() -> None:
    from fastapi import HTTPException

    from adcopilot.interfaces.api.telegram import telegram_webhook

    tg_app = MagicMock()
    request = _make_request(body={}, app_state_tg_app=tg_app)

    with pytest.raises(HTTPException) as exc_info:
        await telegram_webhook(
            request=request,
            settings=_make_settings(),
            x_telegram_bot_api_secret_token=None,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_webhook_returns_503_when_app_not_initialised() -> None:
    from fastapi import HTTPException

    from adcopilot.interfaces.api.telegram import telegram_webhook

    # No telegram_app in state
    request = _make_request(body={}, app_state_tg_app=None)

    with pytest.raises(HTTPException) as exc_info:
        await telegram_webhook(
            request=request,
            settings=_make_settings(),
            x_telegram_bot_api_secret_token=_SECRET,
        )

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_webhook_returns_503_when_no_bot_token() -> None:
    from fastapi import HTTPException

    from adcopilot.interfaces.api.telegram import telegram_webhook

    tg_app = MagicMock()
    request = _make_request(body={}, app_state_tg_app=tg_app)

    with pytest.raises(HTTPException) as exc_info:
        await telegram_webhook(
            request=request,
            settings=_make_settings(bot_token=None),
            x_telegram_bot_api_secret_token=_SECRET,
        )

    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# resolve_webhook_secret — explicit TELEGRAM_WEBHOOK_SECRET takes precedence
# ---------------------------------------------------------------------------


def test_resolve_prefers_explicit_secret_over_derived() -> None:
    settings = _make_settings(webhook_secret="explicit-value")
    assert resolve_webhook_secret(settings) == "explicit-value"


def test_resolve_falls_back_to_hmac_when_secret_unset() -> None:
    settings = _make_settings(webhook_secret=None)
    assert resolve_webhook_secret(settings) == _SECRET


def test_resolve_raises_when_both_missing() -> None:
    settings = _make_settings(bot_token=None, webhook_secret=None)
    with pytest.raises(RuntimeError, match="No Telegram webhook secret"):
        resolve_webhook_secret(settings)


@pytest.mark.asyncio
async def test_webhook_accepts_explicit_secret_from_env() -> None:
    """When TELEGRAM_WEBHOOK_SECRET is set, the header must match it.

    Acceptance criterion: a valid explicit secret is accepted.
    """
    from adcopilot.interfaces.api.telegram import telegram_webhook

    tg_app = MagicMock()
    tg_app.bot = MagicMock()
    tg_app.process_update = AsyncMock()

    request = _make_request(body={"update_id": 1}, app_state_tg_app=tg_app)
    settings = _make_settings(webhook_secret="rotated-secret-123")

    with patch("adcopilot.interfaces.api.telegram.Update.de_json", return_value=MagicMock()):
        result = await telegram_webhook(
            request=request,
            settings=settings,
            x_telegram_bot_api_secret_token="rotated-secret-123",
        )
    assert result == {"ok": "true"}


@pytest.mark.asyncio
async def test_webhook_rejects_hmac_when_explicit_secret_set() -> None:
    """A request signed with the HMAC fallback must be rejected once the
    explicit secret is in use — prevents attackers from replaying pre-rotation
    values."""
    from fastapi import HTTPException

    from adcopilot.interfaces.api.telegram import telegram_webhook

    tg_app = MagicMock()
    request = _make_request(body={}, app_state_tg_app=tg_app)
    settings = _make_settings(webhook_secret="new-rotated-secret")

    with pytest.raises(HTTPException) as exc_info:
        await telegram_webhook(
            request=request,
            settings=settings,
            # Old HMAC-derived secret — must now be rejected.
            x_telegram_bot_api_secret_token=_SECRET,
        )
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# polling guard
# ---------------------------------------------------------------------------


def test_polling_script_exits_in_production() -> None:
    """run_bot.py must sys.exit(1) when ENV=production."""
    import importlib

    # Reload the module so patching get_settings takes effect cleanly.
    mock_settings = MagicMock()
    mock_settings.is_production = True

    with (
        patch("adcopilot.config.get_settings", return_value=mock_settings),
        pytest.raises(SystemExit) as exc_info,
    ):
        import scripts.run_bot as run_bot_module

        importlib.reload(run_bot_module)
        # Simulate calling main() directly
        with patch("scripts.run_bot.get_settings", return_value=mock_settings):
            run_bot_module.main()

    assert exc_info.value.code == 1
