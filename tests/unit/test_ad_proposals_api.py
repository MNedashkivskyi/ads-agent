"""Unit tests for ad copy proposal API endpoints (Task 3.5)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _jwt(user_id: str = "user-123") -> dict:
    from jose import jwt

    from adcopilot.config import get_settings

    token = jwt.encode({"sub": user_id}, get_settings().SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client():  # noqa: ANN201
    """App client with the entitlement gate satisfied (Professional).

    The ad-proposal endpoints are gated behind advanced_optimization (T2.2);
    patching the plan loader keeps these auth/ownership tests deterministic and
    independent of a real database. STARTER gating is covered separately below.
    """
    from unittest.mock import AsyncMock, patch

    from adcopilot.domain.entities import PlanTier
    from adcopilot.main import create_app

    with patch(
        "adcopilot.interfaces.api.deps._load_plan",
        new=AsyncMock(return_value=PlanTier.PROFESSIONAL),
    ):
        yield TestClient(create_app(), raise_server_exceptions=False)


def test_on_demand_variants_blocked_for_starter() -> None:
    """On-demand RSA variant generation is gated behind advanced_optimization;
    a STARTER user is rejected with 403 (T2.2)."""
    from unittest.mock import AsyncMock, patch

    from adcopilot.domain.entities import PlanTier
    from adcopilot.main import create_app

    with patch(
        "adcopilot.interfaces.api.deps._load_plan",
        new=AsyncMock(return_value=PlanTier.STARTER),
    ):
        c = TestClient(create_app(), raise_server_exceptions=False)
        resp = c.post(
            "/api/user-123/ad-copy/variants",
            headers=_jwt("user-123"),
            json={"campaign_name": "Test", "vertical": "salon"},
        )
    assert resp.status_code == 403


def test_get_proposals_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/user-123/recommendations/rec-1/ad-proposals")
    assert resp.status_code == 401


def test_get_proposals_denies_wrong_user(client: TestClient) -> None:
    resp = client.get(
        "/api/user-123/recommendations/rec-1/ad-proposals",
        headers=_jwt("other"),
    )
    assert resp.status_code == 403


def test_approve_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/user-123/recommendations/rec-1/ad-proposals/approve")
    assert resp.status_code == 401


def test_approve_denies_wrong_user(client: TestClient) -> None:
    resp = client.post(
        "/api/user-123/recommendations/rec-1/ad-proposals/approve",
        headers=_jwt("other"),
    )
    assert resp.status_code == 403


def test_approve_response_schema() -> None:
    from adcopilot.interfaces.api.ad_proposals import ApproveProposalResponse

    r = ApproveProposalResponse(
        rec_id="rec-1",
        status="APPROVED",
        message="Rekomendacja zatwierdzona. Odświeżanie reklam zostało zakolejkowane.",
    )
    assert r.status == "APPROVED"
    assert "zatwierdzona" in r.message


def test_ad_proposal_response_schema() -> None:
    from adcopilot.interfaces.api.ad_proposals import AdProposalResponse

    r = AdProposalResponse(
        headlines=["H1", "H2", "H3"],
        descriptions=["D1", "D2"],
        final_url="https://example.com",
    )
    assert len(r.headlines) == 3
    assert len(r.descriptions) == 2


def test_approve_message_is_polish() -> None:
    from adcopilot.interfaces.api.ad_proposals import ApproveProposalResponse

    r = ApproveProposalResponse(
        rec_id="x",
        status="APPROVED",
        message="Rekomendacja zatwierdzona. Odświeżanie reklam zostało zakolejkowane.",
    )
    assert "zakolejkowane" in r.message
