"""Unit tests for the undo-recommendation API endpoint (ADW-001)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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


_URL = "/api/users/user-123/recommendations/rec-1/undo"


def test_undo_requires_auth(client: TestClient) -> None:
    resp = client.post(_URL)
    assert resp.status_code == 401


def test_undo_denies_wrong_user(client: TestClient) -> None:
    resp = client.post(_URL, headers=_jwt("someone-else"))
    assert resp.status_code == 403


@patch(
    "adcopilot.infrastructure.db.repositories.recommendation_repository.SqlRecommendationRepository"
)
def test_undo_rejects_non_executed(mock_repo_cls: MagicMock, client: TestClient) -> None:
    from adcopilot.domain.recommendation import RecommendationStatus

    rec = MagicMock()
    rec.status = RecommendationStatus.PENDING
    repo = MagicMock()
    repo.get = AsyncMock(return_value=rec)
    mock_repo_cls.return_value = repo

    resp = client.post(_URL, headers=_jwt("user-123"))
    assert resp.status_code == 409


@patch(
    "adcopilot.infrastructure.db.repositories.recommendation_repository.SqlRecommendationRepository"
)
def test_undo_returns_404_when_missing(mock_repo_cls: MagicMock, client: TestClient) -> None:
    repo = MagicMock()
    repo.get = AsyncMock(return_value=None)
    mock_repo_cls.return_value = repo

    resp = client.post(_URL, headers=_jwt("user-123"))
    assert resp.status_code == 404
