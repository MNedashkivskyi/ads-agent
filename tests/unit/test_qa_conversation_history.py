"""Tests for Q&A conversation history — Task 5.4."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adcopilot.infrastructure.db.repositories.qa_conversation_repository import (
    QaConversation,
    SqlQaConversationRepository,
)

# ---------------------------------------------------------------------------
# Repository unit tests
# ---------------------------------------------------------------------------

def _make_model(
    user_id: str = "user-1",
    account_id: str | None = "acc-1",
    question: str = "Jak idzie kampania?",
    answer: str = "Kampania działa dobrze.",
) -> MagicMock:
    m = MagicMock()
    m.id = uuid.uuid4()
    m.user_id = user_id
    m.account_id = account_id
    m.question = question
    m.answer = answer
    m.context_snapshot = {"summary": {"spend": 100.0}}
    m.created_at = datetime(2026, 5, 19, 8, 0, tzinfo=UTC)
    return m


@pytest.mark.asyncio
async def test_save_returns_domain_object():
    session = AsyncMock()
    session.flush = AsyncMock()
    repo = SqlQaConversationRepository(session)

    result = await repo.save(
        user_id="user-1",
        account_id="acc-1",
        question="Co to jest ROAS?",
        answer="ROAS to zwrot z wydatków na reklamę.",
    )

    session.add.assert_called_once()
    session.flush.assert_awaited_once()
    assert isinstance(result, QaConversation)
    assert result.user_id == "user-1"
    assert result.account_id == "acc-1"
    assert result.question == "Co to jest ROAS?"
    assert result.answer == "ROAS to zwrot z wydatków na reklamę."
    assert result.context_snapshot is None


@pytest.mark.asyncio
async def test_save_with_context_snapshot():
    session = AsyncMock()
    session.flush = AsyncMock()
    repo = SqlQaConversationRepository(session)

    ctx = {"snapshot_date": "2026-05-19", "summary": {"spend": 500.0}}
    result = await repo.save(
        user_id="u1",
        account_id=None,
        question="Ile wydałem?",
        answer="500 zł.",
        context_snapshot=ctx,
    )

    assert result.context_snapshot == ctx
    assert result.account_id is None


@pytest.mark.asyncio
async def test_list_for_user_returns_domain_objects():
    model = _make_model()
    session = AsyncMock()
    scalars_result = MagicMock()
    scalars_result.__iter__ = MagicMock(return_value=iter([model]))
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars_result)
    session.execute = AsyncMock(return_value=execute_result)

    repo = SqlQaConversationRepository(session)
    items = await repo.list_for_user(user_id="user-1", limit=10, offset=0)

    assert len(items) == 1
    assert items[0].user_id == "user-1"
    assert items[0].question == "Jak idzie kampania?"


@pytest.mark.asyncio
async def test_list_for_user_empty():
    session = AsyncMock()
    scalars_result = MagicMock()
    scalars_result.__iter__ = MagicMock(return_value=iter([]))
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars_result)
    session.execute = AsyncMock(return_value=execute_result)

    repo = SqlQaConversationRepository(session)
    items = await repo.list_for_user(user_id="no-such-user")
    assert items == []


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

def _mock_qa_history_items() -> list[QaConversation]:
    return [
        QaConversation(
            id=str(uuid.uuid4()),
            user_id="user-1",
            account_id="acc-1",
            question="Jak idzie?",
            answer="Dobrze.",
            context_snapshot=None,
            created_at=datetime(2026, 5, 19, 10, 0, tzinfo=UTC),
        ),
        QaConversation(
            id=str(uuid.uuid4()),
            user_id="user-1",
            account_id=None,
            question="Ile wydałem?",
            answer="500 zł.",
            context_snapshot={"summary": {}},
            created_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
        ),
    ]


@pytest.mark.asyncio
async def test_qa_history_endpoint_returns_items():
    from fastapi.testclient import TestClient

    from adcopilot.interfaces.api.qa import router

    items = _mock_qa_history_items()

    mock_repo_instance = AsyncMock()
    mock_repo_instance.list_for_user = AsyncMock(return_value=items)

    mock_session_instance = AsyncMock()
    mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
    mock_session_instance.__aexit__ = AsyncMock(return_value=False)
    mock_session_instance.begin = MagicMock(return_value=mock_session_instance)

    import sqlalchemy.ext.asyncio as sqla_async

    import adcopilot.infrastructure.db.repositories.qa_conversation_repository as qa_repo_mod

    with (
        patch.object(qa_repo_mod, "SqlQaConversationRepository", return_value=mock_repo_instance),
        patch.object(sqla_async, "create_async_engine", return_value=MagicMock(dispose=AsyncMock())),
        patch.object(sqla_async, "AsyncSession", return_value=mock_session_instance),
    ):

        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        from adcopilot.interfaces.api.auth_middleware import get_current_user

        async def override_auth():
            return "user-1"

        app.dependency_overrides[get_current_user] = override_auth

        from adcopilot.config import get_settings

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://test"
        app.dependency_overrides[get_settings] = lambda: mock_settings

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/user-1/qa-history?limit=10&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert len(data["items"]) == 2
    assert data["items"][0]["question"] == "Jak idzie?"
    assert data["items"][1]["answer"] == "500 zł."


@pytest.mark.asyncio
async def test_qa_history_endpoint_forbidden():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from adcopilot.interfaces.api.auth_middleware import get_current_user
    from adcopilot.interfaces.api.qa import router

    app = FastAPI()
    app.include_router(router)

    async def override_auth():
        return "other-user"

    app.dependency_overrides[get_current_user] = override_auth

    from adcopilot.config import get_settings

    mock_settings = MagicMock()
    mock_settings.DATABASE_URL = "postgresql+asyncpg://test"
    app.dependency_overrides[get_settings] = lambda: mock_settings

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/user-1/qa-history")
    assert response.status_code == 403
