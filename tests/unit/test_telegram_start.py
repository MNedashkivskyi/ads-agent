"""
Unit tests for the Telegram /start command handler using fake UserRepository.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone

UTC = timezone.utc
from unittest.mock import AsyncMock, MagicMock, patch

from adcopilot.domain.entities import PlanTier, User, UserId
from adcopilot.interfaces.api.telegram import _make_link_token, _verify_link_token


def _make_redis_mock(stored: dict[str, str] | None = None) -> MagicMock:
    """Return a mock Redis client that stores keys in a plain dict."""
    data: dict[str, str] = stored or {}

    mock = MagicMock()

    def _set(key: str, value: str, ex: int | None = None) -> None:
        data[key] = value

    def _get(key: str) -> bytes | None:
        val = data.get(key)
        return val.encode() if val is not None else None

    def _delete(key: str) -> None:
        data.pop(key, None)

    mock.set.side_effect = _set
    mock.get.side_effect = _get
    mock.delete.side_effect = _delete
    return mock


def _make_user(**kwargs: object) -> User:
    defaults: dict[str, object] = {
        "id": UserId(str(uuid.uuid4())),
        "email": "alice@example.com",
        "telegram_chat_id": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "plan": PlanTier.STARTER,
    }
    defaults.update(kwargs)
    return User(**defaults)  # type: ignore[arg-type]


def test_make_and_verify_link_token_roundtrip() -> None:
    user_id = str(uuid.uuid4())
    redis = _make_redis_mock()
    token = _make_link_token(user_id, redis)
    # Token must be 32 hex chars — valid Telegram start payload
    assert len(token) == 32
    assert all(c in "0123456789abcdef" for c in token)
    result = _verify_link_token(token, redis)
    assert result == user_id


def test_verify_link_token_single_use() -> None:
    user_id = str(uuid.uuid4())
    redis = _make_redis_mock()
    token = _make_link_token(user_id, redis)
    assert _verify_link_token(token, redis) == user_id
    # Second use returns None — token was consumed
    assert _verify_link_token(token, redis) is None


def test_verify_link_token_missing_returns_none() -> None:
    redis = _make_redis_mock()
    assert _verify_link_token("nonexistent" * 3, redis) is None


def _make_async_update(chat_id: int = 123) -> MagicMock:
    update = MagicMock()
    update.message = MagicMock()
    update.message.chat_id = chat_id
    update.message.reply_text = AsyncMock()
    return update


@patch("adcopilot.infrastructure.telegram.handlers.redis_sync")
@patch("adcopilot.infrastructure.telegram.handlers.get_settings")
@patch("adcopilot.infrastructure.telegram.handlers.create_async_engine")
async def test_start_with_valid_token_links_account(
    mock_engine: MagicMock,
    mock_get_settings: MagicMock,
    mock_redis_module: MagicMock,
) -> None:
    from adcopilot.config import Settings
    from adcopilot.infrastructure.telegram.handlers import start_handler

    settings = Settings(REDIS_URL="redis://localhost:6379/0")
    mock_get_settings.return_value = settings

    user_id = str(uuid.uuid4())
    user = _make_user(id=UserId(user_id))

    # Set up a fake Redis with the token already stored
    redis_data: dict[str, str] = {}
    fake_redis = _make_redis_mock(redis_data)
    token = _make_link_token(user_id, fake_redis)
    mock_redis_module.Redis.from_url.return_value = fake_redis

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = user
    updated_user = dataclasses.replace(user, telegram_chat_id=999)
    mock_repo.save.return_value = updated_user

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_engine_instance = MagicMock()
    mock_engine.return_value = mock_engine_instance
    mock_engine_instance.dispose = AsyncMock()

    async_ctx = MagicMock()
    async_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    async_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "adcopilot.infrastructure.telegram.handlers.AsyncSession",
        return_value=async_ctx,
    ), patch(
        "adcopilot.infrastructure.telegram.handlers.SqlUserRepository",
        return_value=mock_repo,
    ):
        update = _make_async_update(chat_id=999)
        context = MagicMock()
        context.args = [token]

        await start_handler(update, context)

    update.message.reply_text.assert_called_once()
    call_text: str = update.message.reply_text.call_args[0][0]
    assert "połączon" in call_text.lower() or "witaj" in call_text.lower()


@patch("adcopilot.infrastructure.telegram.handlers.get_settings")
async def test_start_without_args_sends_instructions(mock_get_settings: MagicMock) -> None:
    from adcopilot.config import Settings
    from adcopilot.infrastructure.telegram.handlers import start_handler

    mock_get_settings.return_value = Settings()

    update = _make_async_update()
    context = MagicMock()
    context.args = []

    await start_handler(update, context)

    update.message.reply_text.assert_called_once()
    call_text: str = update.message.reply_text.call_args[0][0]
    assert "adswise" in call_text.lower()


@patch("adcopilot.infrastructure.telegram.handlers.redis_sync")
@patch("adcopilot.infrastructure.telegram.handlers.get_settings")
async def test_start_with_invalid_token_sends_error(
    mock_get_settings: MagicMock,
    mock_redis_module: MagicMock,
) -> None:
    from adcopilot.config import Settings
    from adcopilot.infrastructure.telegram.handlers import start_handler

    mock_get_settings.return_value = Settings(REDIS_URL="redis://localhost:6379/0")

    fake_redis = _make_redis_mock()
    mock_redis_module.Redis.from_url.return_value = fake_redis

    update = _make_async_update()
    context = MagicMock()
    context.args = ["invalidtoken000000000000000000000"]

    await start_handler(update, context)

    update.message.reply_text.assert_called_once()
    call_text: str = update.message.reply_text.call_args[0][0]
    assert "link" in call_text.lower() or "wygasł" in call_text.lower()
