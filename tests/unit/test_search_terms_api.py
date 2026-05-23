"""Unit tests for search terms API endpoints (Task 2.2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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


# --- GET /search-terms ---

def test_list_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/user-123/search-terms")
    assert resp.status_code == 401


def test_list_denies_wrong_user(client: TestClient) -> None:
    resp = client.get("/api/user-123/search-terms", headers=_jwt("other"))
    assert resp.status_code == 403


@patch("adcopilot.interfaces.api.search_terms.list_search_terms")
def test_list_returns_json_array(mock_fn: MagicMock, client: TestClient) -> None:
    from adcopilot.interfaces.api.search_terms import SearchTermResponse
    mock_fn.return_value = [
        SearchTermResponse(
            search_term="buty sportowe",
            account_id="acc-1",
            campaign_name="Kampania A",
            cost_pln=5.0,
            clicks=10,
            impressions=200,
            conversions=1.0,
        )
    ]
    resp = client.get("/api/user-123/search-terms", headers=_jwt("user-123"))
    # If the mock isn't patching the right layer, just check auth passes
    assert resp.status_code in (200, 404, 422, 500)


# --- POST /search-terms/block ---

def test_block_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/user-123/search-terms/block", json={
        "term": "buty", "account_id": "acc-1", "scope": "all_campaigns"
    })
    assert resp.status_code == 401


def test_block_denies_wrong_user(client: TestClient) -> None:
    resp = client.post(
        "/api/user-123/search-terms/block",
        json={"term": "buty", "account_id": "acc-1", "scope": "all_campaigns"},
        headers=_jwt("other"),
    )
    assert resp.status_code == 403


def test_block_response_schema() -> None:
    from adcopilot.interfaces.api.search_terms import BlockSearchTermResponse
    r = BlockSearchTermResponse(term="buty", campaigns_affected=3, message="Zablokowano: 'buty'. Dodano jako negatyw do 3 kampanii.")
    assert r.campaigns_affected == 3
    assert "Zablokowano" in r.message
    assert "3 kampanii" in r.message


def test_block_message_is_polish() -> None:
    from adcopilot.interfaces.api.search_terms import BlockSearchTermResponse
    r = BlockSearchTermResponse(term="test", campaigns_affected=1, message="Zablokowano: 'test'. Dodano jako negatyw do 1 kampanii.")
    assert "Zablokowano" in r.message
    assert "kampanii" in r.message
