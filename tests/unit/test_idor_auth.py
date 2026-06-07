"""LAUNCH-002: notifications / snapshots / digest require auth + ownership."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _jwt(user_id: str = "user-123") -> dict:
    from jose import jwt

    from adcopilot.config import get_settings

    token = jwt.encode({"sub": user_id}, get_settings().SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client() -> TestClient:
    from adcopilot.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


# --- notifications (user_id is a query param) ---
def test_notifications_list_requires_auth(client: TestClient) -> None:
    assert client.get("/api/notifications?user_id=user-123").status_code == 401


def test_notifications_list_denies_wrong_user(client: TestClient) -> None:
    r = client.get("/api/notifications?user_id=user-123", headers=_jwt("attacker"))
    assert r.status_code == 403


def test_notifications_unread_count_denies_wrong_user(client: TestClient) -> None:
    r = client.get("/api/notifications/unread-count?user_id=user-123", headers=_jwt("attacker"))
    assert r.status_code == 403


def test_notifications_mark_all_read_requires_auth(client: TestClient) -> None:
    assert client.post("/api/notifications/mark-all-read?user_id=user-123").status_code == 401


# --- digest ---
def test_digest_requires_auth(client: TestClient) -> None:
    assert client.post("/api/users/user-123/digest").status_code == 401


def test_digest_denies_wrong_user(client: TestClient) -> None:
    assert client.post("/api/users/user-123/digest", headers=_jwt("attacker")).status_code == 403


# --- snapshots (account-scoped) ---
def test_snapshot_trigger_requires_auth(client: TestClient) -> None:
    assert client.post("/api/accounts/acc-1/snapshots").status_code == 401


def test_snapshot_latest_requires_auth(client: TestClient) -> None:
    assert client.get("/api/accounts/acc-1/snapshots/latest").status_code == 401
