"""
Unit tests for the Telegram /start command handler using fake UserRepository.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from adcopilot.domain.entities import PlanTier, User, UserId
from adcopilot.interfaces.api.telegram import _make_link_jwt, _verify_link_jwt

SECRET_KEY = "test-secret-key"


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


def test_make_and_verify_link_jwt_roundtrip() -> None:
    user_id = str(uuid.uuid4())
    token = _make_link_jwt(user_id, SECRET_KEY)
    result = _verify_link_jwt(token, SECRET_KEY)
    assert result == user_id


def test_verify_link_jwt_wrong_key_returns_none() -> None:
    token = _make_link_jwt("user-1", SECRET_KEY)
    result = _verify_link_jwt(token, "wrong-key")
    assert result is None


def test_verify_link_jwt_invalid_token_returns_none() -> None:
    result = _verify_link_jwt("not.a.jwt", SECRET_KEY)
    assert result is None


def _make_async_update(chat_id: int = 123) -> MagicMock:
    update = MagicMock()
    update.message = MagicMock()
    update.message.chat_id = chat_id
    update.message.reply_text = AsyncMock()
    return update


@patch("adcopilot.infrastructure.telegram.handlers.get_settings")
@patch("adcopilot.infrastructure.telegram.handlers.create_async_engine")
async def test_start_with_valid_token_links_account(
    mock_engine: MagicMock,
    mock_get_settings: MagicMock,
) -> None:
    from adcopilot.config import Settings
    from adcopilot.infrastructure.telegram.handlers import start_handler

    settings = Settings(SECRET_KEY=SECRET_KEY)
    mock_get_settings.return_value = settings

    user_id = str(uuid.uuid4())
    user = _make_user(id=UserId(user_id))
    token = _make_link_jwt(user_id, SECRET_KEY)

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = user
    updated_user = dataclasses.replace(user, telegram_chat_id=999)
    mock_repo.save.return_value = updated_user

    # Mock the AsyncSession context manager
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
    assert "linked" in call_text.lower() or "welcome" in call_text.lower()


@patch("adcopilot.infrastructure.telegram.handlers.get_settings")
async def test_start_without_args_sends_instructions(mock_get_settings: MagicMock) -> None:
    from adcopilot.config import Settings
    from adcopilot.infrastructure.telegram.handlers import start_handler

    mock_get_settings.return_value = Settings(SECRET_KEY=SECRET_KEY)

    update = _make_async_update()
    context = MagicMock()
    context.args = []

    await start_handler(update, context)

    update.message.reply_text.assert_called_once()
    call_text: str = update.message.reply_text.call_args[0][0]
    assert "sign up" in call_text.lower() or "welcome" in call_text.lower()


@patch("adcopilot.infrastructure.telegram.handlers.get_settings")
async def test_start_with_invalid_token_sends_error(mock_get_settings: MagicMock) -> None:
    from adcopilot.config import Settings
    from adcopilot.infrastructure.telegram.handlers import start_handler

    mock_get_settings.return_value = Settings(SECRET_KEY=SECRET_KEY)

    update = _make_async_update()
    context = MagicMock()
    context.args = ["invalid-token"]

    await start_handler(update, context)

    update.message.reply_text.assert_called_once()
    call_text: str = update.message.reply_text.call_args[0][0]
    assert "invalid" in call_text.lower() or "expired" in call_text.lower()
