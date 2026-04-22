"""Tests for the dashboard API endpoints and auth middleware."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt

# ---------------------------------------------------------------------------
# Auth middleware tests
# ---------------------------------------------------------------------------

_ALGORITHM = "HS256"
_SECRET = "test-secret-key"


def _make_token(user_id: str, secret: str = _SECRET, expired: bool = False) -> str:
    exp = datetime.now(UTC) + (timedelta(days=-1) if expired else timedelta(days=30))
    return jwt.encode({"sub": user_id, "exp": exp}, secret, algorithm=_ALGORITHM)


def test_get_current_user_valid_token() -> None:
    from adcopilot.interfaces.api.auth_middleware import get_current_user
    from fastapi.security import HTTPAuthorizationCredentials

    settings = MagicMock()
    settings.SECRET_KEY = _SECRET

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=_make_token("user-42"))
    result = get_current_user(creds, settings)
    assert result == "user-42"


def test_get_current_user_missing_token_raises_401() -> None:
    from adcopilot.interfaces.api.auth_middleware import get_current_user

    settings = MagicMock()
    settings.SECRET_KEY = _SECRET

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(None, settings)
    assert exc_info.value.status_code == 401


def test_get_current_user_expired_token_raises_401() -> None:
    from adcopilot.interfaces.api.auth_middleware import get_current_user
    from fastapi.security import HTTPAuthorizationCredentials

    settings = MagicMock()
    settings.SECRET_KEY = _SECRET

    creds = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=_make_token("user-42", expired=True)
    )
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(creds, settings)
    assert exc_info.value.status_code == 401


def test_get_current_user_malformed_token_raises_401() -> None:
    from adcopilot.interfaces.api.auth_middleware import get_current_user
    from fastapi.security import HTTPAuthorizationCredentials

    settings = MagicMock()
    settings.SECRET_KEY = _SECRET

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not.a.valid.jwt")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(creds, settings)
    assert exc_info.value.status_code == 401


def test_get_current_user_wrong_secret_raises_401() -> None:
    from adcopilot.interfaces.api.auth_middleware import get_current_user
    from fastapi.security import HTTPAuthorizationCredentials

    settings = MagicMock()
    settings.SECRET_KEY = "different-secret"

    creds = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=_make_token("user-42", secret=_SECRET)
    )
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(creds, settings)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Dashboard endpoint 403 guard tests (no DB needed)
# ---------------------------------------------------------------------------


def _build_app() -> "FastAPI":
    """Build a minimal FastAPI app with the dashboard router for testing."""
    from fastapi import FastAPI

    from adcopilot.interfaces.api.dashboard import router

    app = FastAPI()
    app.include_router(router)
    return app


def _auth_header(user_id: str, secret: str = _SECRET) -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token(user_id, secret=secret)}"}


@pytest.fixture()
def client_and_override():
    """TestClient with get_settings overridden to avoid real DB."""
    from fastapi import FastAPI
    from adcopilot.interfaces.api.dashboard import router
    from adcopilot.config import get_settings

    app = FastAPI()
    app.include_router(router)

    settings_mock = MagicMock()
    settings_mock.SECRET_KEY = _SECRET
    settings_mock.DATABASE_URL = "postgresql+asyncpg://fake/fake"

    app.dependency_overrides[get_settings] = lambda: settings_mock
    return TestClient(app, raise_server_exceptions=False)


def test_performance_endpoint_forbidden_for_different_user(client_and_override) -> None:
    client = client_and_override
    resp = client.get(
        "/api/dashboard/user-other/performance",
        headers=_auth_header("user-me"),
    )
    assert resp.status_code == 403


def test_impact_endpoint_forbidden_for_different_user(client_and_override) -> None:
    client = client_and_override
    resp = client.get(
        "/api/dashboard/user-other/recommendations/impact",
        headers=_auth_header("user-me"),
    )
    assert resp.status_code == 403


def test_structure_endpoint_forbidden_for_different_user(client_and_override) -> None:
    client = client_and_override
    resp = client.get(
        "/api/dashboard/user-other/campaigns/structure",
        headers=_auth_header("user-me"),
    )
    assert resp.status_code == 403


def test_benchmarks_endpoint_forbidden_for_different_user(client_and_override) -> None:
    client = client_and_override
    resp = client.get(
        "/api/dashboard/user-other/benchmarks",
        headers=_auth_header("user-me"),
    )
    assert resp.status_code == 403


def test_performance_endpoint_requires_auth(client_and_override) -> None:
    client = client_and_override
    resp = client.get("/api/dashboard/user-1/performance")
    assert resp.status_code == 401
