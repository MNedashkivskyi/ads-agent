"""Admin set-plan endpoint — auth guard + validation (no DB required).

The admin check and plan/identifier validation all run before any DB access, so
these paths are exercised without a database.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def client_factory():  # noqa: ANN201
    from fastapi.testclient import TestClient

    from adcopilot.config import Settings, get_settings
    from adcopilot.interfaces.api.auth_middleware import get_current_user
    from adcopilot.main import create_app

    def _make(*, current_user: str, admin_ids: str):
        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: current_user
        app.dependency_overrides[get_settings] = lambda: Settings(ADMIN_USER_IDS=admin_ids)
        return TestClient(app, raise_server_exceptions=False)

    return _make


def test_non_admin_forbidden(client_factory) -> None:  # noqa: ANN001
    c = client_factory(current_user="user-1", admin_ids="")  # empty allow-list → no admins
    resp = c.post("/api/admin/users/plan", json={"plan": "business", "email": "x@y.z"})
    assert resp.status_code == 403


def test_admin_rejects_invalid_plan(client_factory) -> None:  # noqa: ANN001
    c = client_factory(current_user="admin-1", admin_ids="admin-1")
    resp = c.post("/api/admin/users/plan", json={"plan": "platinum", "email": "x@y.z"})
    assert resp.status_code == 422
    assert "Invalid plan" in resp.text


def test_admin_requires_identifier(client_factory) -> None:  # noqa: ANN001
    c = client_factory(current_user="admin-1", admin_ids="admin-1")
    resp = c.post("/api/admin/users/plan", json={"plan": "business"})
    assert resp.status_code == 422
    assert "Provide user_id or email" in resp.text


def test_admin_rejects_bad_uuid(client_factory) -> None:  # noqa: ANN001
    # Reaches the DB-lookup branch; a malformed uuid is rejected as 422 (not 500).
    c = client_factory(current_user="admin-1", admin_ids="admin-1")
    resp = c.post(
        "/api/admin/users/plan", json={"plan": "business", "user_id": "not-a-uuid"}
    )
    assert resp.status_code == 422
