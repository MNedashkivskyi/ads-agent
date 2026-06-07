"""LAUNCH-003: user read endpoints enforce ownership (no cross-user reads)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _jwt(user_id: str) -> dict:
    from jose import jwt

    from adcopilot.config import get_settings

    return {"Authorization": f"Bearer {jwt.encode({'sub': user_id}, get_settings().SECRET_KEY, algorithm='HS256')}"}


@pytest.fixture
def client() -> TestClient:
    from adcopilot.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


_PATHS = [
    "/api/users/user-123/stats",
    "/api/users/user-123/recommendations",
    "/api/users/user-123/recommendations/last-refreshed",
    "/api/users/user-123/audit-log",
]


@pytest.mark.parametrize("path", _PATHS)
def test_requires_auth(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", _PATHS)
def test_denies_wrong_user(client: TestClient, path: str) -> None:
    assert client.get(path, headers=_jwt("attacker")).status_code == 403
