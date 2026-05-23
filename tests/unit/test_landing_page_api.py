"""Unit tests for landing page score API endpoints (Task 4.3)."""

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


def test_score_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/user-123/landing-page/score?url=https://example.com")
    assert resp.status_code == 401


def test_score_denies_wrong_user(client: TestClient) -> None:
    resp = client.get(
        "/api/user-123/landing-page/score?url=https://example.com",
        headers=_jwt("other"),
    )
    assert resp.status_code == 403


def test_score_response_schema() -> None:
    from datetime import UTC, datetime

    from adcopilot.interfaces.api.landing_page import (
        CoreWebVitalsResponse,
        LandingPageScoreResponse,
    )

    r = LandingPageScoreResponse(
        url="https://example.com",
        performance_score=72,
        accessibility_score=85,
        seo_score=90,
        best_practices_score=78,
        mobile_friendly=True,
        core_web_vitals=CoreWebVitalsResponse(lcp_ms=2500.0, fcp_ms=1100.0),
        recommendations_pl=["Rec 1", "Rec 2", "Rec 3"],
        scored_at=datetime.now(UTC).isoformat(),
    )
    assert r.performance_score == 72
    assert len(r.recommendations_pl) == 3
    assert r.mobile_friendly is True


def test_core_web_vitals_defaults_none() -> None:
    from adcopilot.interfaces.api.landing_page import CoreWebVitalsResponse

    cwv = CoreWebVitalsResponse()
    assert cwv.lcp_ms is None
    assert cwv.cls_score is None
