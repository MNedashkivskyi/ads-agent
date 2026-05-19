"""Tests for weekly insight history storage and retrieval — Task 5.5."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adcopilot.infrastructure.db.repositories.weekly_insight_repository import (
    SqlWeeklyInsightRepository,
    WeeklyInsight,
)


# ---------------------------------------------------------------------------
# Repository unit tests
# ---------------------------------------------------------------------------

def _make_model(
    user_id: str = "user-1",
    account_id: str | None = "acc-1",
    week_start: date = date(2026, 5, 18),
    insight_text: str = "Kampania działa dobrze.",
) -> MagicMock:
    m = MagicMock()
    m.id = uuid.uuid4()
    m.user_id = user_id
    m.account_id = account_id
    m.week_start = week_start
    m.insight_text = insight_text
    m.context_snapshot = {"summary": {"spend": 200.0}}
    m.created_at = datetime(2026, 5, 19, 8, 30, tzinfo=timezone.utc)
    return m


@pytest.mark.asyncio
async def test_save_returns_domain_object():
    session = AsyncMock()
    session.flush = AsyncMock()
    repo = SqlWeeklyInsightRepository(session)

    result = await repo.save(
        user_id="user-1",
        account_id="acc-1",
        week_start=date(2026, 5, 18),
        insight_text="Twoje kampanie osiągnęły ROAS 3.2.",
    )

    session.add.assert_called_once()
    session.flush.assert_awaited_once()
    assert isinstance(result, WeeklyInsight)
    assert result.user_id == "user-1"
    assert result.account_id == "acc-1"
    assert result.week_start == date(2026, 5, 18)
    assert result.insight_text == "Twoje kampanie osiągnęły ROAS 3.2."
    assert result.context_snapshot is None


@pytest.mark.asyncio
async def test_save_with_context_snapshot():
    session = AsyncMock()
    session.flush = AsyncMock()
    repo = SqlWeeklyInsightRepository(session)

    ctx = {"snapshot_date": "2026-05-19", "summary": {"spend": 999.0}}
    result = await repo.save(
        user_id="u1",
        account_id=None,
        week_start=date(2026, 5, 11),
        insight_text="Insight.",
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

    repo = SqlWeeklyInsightRepository(session)
    items = await repo.list_for_user(user_id="user-1", limit=10, offset=0)

    assert len(items) == 1
    assert items[0].user_id == "user-1"
    assert items[0].week_start == date(2026, 5, 18)


@pytest.mark.asyncio
async def test_list_for_user_empty():
    session = AsyncMock()
    scalars_result = MagicMock()
    scalars_result.__iter__ = MagicMock(return_value=iter([]))
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars_result)
    session.execute = AsyncMock(return_value=execute_result)

    repo = SqlWeeklyInsightRepository(session)
    items = await repo.list_for_user(user_id="no-such-user")
    assert items == []


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

def _mock_insight_items() -> list[WeeklyInsight]:
    return [
        WeeklyInsight(
            id=str(uuid.uuid4()),
            user_id="user-1",
            account_id="acc-1",
            week_start=date(2026, 5, 18),
            insight_text="Tydzień był udany.",
            context_snapshot=None,
            created_at=datetime(2026, 5, 19, 8, 30, tzinfo=timezone.utc),
        ),
        WeeklyInsight(
            id=str(uuid.uuid4()),
            user_id="user-1",
            account_id=None,
            week_start=date(2026, 5, 11),
            insight_text="ROAS wzrósł o 15%.",
            context_snapshot={"summary": {}},
            created_at=datetime(2026, 5, 12, 8, 30, tzinfo=timezone.utc),
        ),
    ]


@pytest.mark.asyncio
async def test_insights_endpoint_returns_items():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from adcopilot.interfaces.api.auth_middleware import get_current_user
    from adcopilot.interfaces.api.insights import router

    items = _mock_insight_items()

    mock_repo_instance = AsyncMock()
    mock_repo_instance.list_for_user = AsyncMock(return_value=items)

    mock_session_instance = AsyncMock()
    mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
    mock_session_instance.__aexit__ = AsyncMock(return_value=False)
    mock_session_instance.begin = MagicMock(return_value=mock_session_instance)

    import adcopilot.infrastructure.db.repositories.weekly_insight_repository as repo_mod
    import sqlalchemy.ext.asyncio as sqla_async

    with (
        patch.object(repo_mod, "SqlWeeklyInsightRepository", return_value=mock_repo_instance),
        patch.object(sqla_async, "create_async_engine", return_value=MagicMock(dispose=AsyncMock())),
        patch.object(sqla_async, "AsyncSession", return_value=mock_session_instance),
    ):
        app = FastAPI()
        app.include_router(router)

        async def override_auth():
            return "user-1"

        app.dependency_overrides[get_current_user] = override_auth

        from adcopilot.config import get_settings

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://test"
        app.dependency_overrides[get_settings] = lambda: mock_settings

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/user-1/insights?limit=10&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert len(data["items"]) == 2
    assert data["items"][0]["week_start"] == "2026-05-18"
    assert data["items"][1]["insight_text"] == "ROAS wzrósł o 15%."


@pytest.mark.asyncio
async def test_insights_endpoint_forbidden():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from adcopilot.interfaces.api.auth_middleware import get_current_user
    from adcopilot.interfaces.api.insights import router

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
    response = client.get("/api/user-1/insights")
    assert response.status_code == 403
