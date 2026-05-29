"""Unit tests for conversion tracking guide endpoint."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adcopilot.interfaces.api.conversion_tracking_guide import router


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_list_platforms_returns_four_options(client):
    resp = client.get("/api/conversion-tracking/guide")
    assert resp.status_code == 200
    data = resp.json()
    platforms = {item["platform"] for item in data}
    assert platforms == {"wordpress", "wix", "squarespace", "other"}


def test_wordpress_guide_has_five_steps(client):
    resp = client.get("/api/conversion-tracking/guide/wordpress")
    assert resp.status_code == 200
    data = resp.json()
    assert data["platform"] == "wordpress"
    assert len(data["steps"]) == 5
    assert data["estimated_minutes"] > 0
    assert data["help_url"].startswith("https://")


def test_wix_guide_returns_correct_platform(client):
    resp = client.get("/api/conversion-tracking/guide/wix")
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Wix"


def test_squarespace_guide_returns_correct_platform(client):
    resp = client.get("/api/conversion-tracking/guide/squarespace")
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Squarespace"


def test_other_guide_returns_correct_platform(client):
    resp = client.get("/api/conversion-tracking/guide/other")
    assert resp.status_code == 200
    assert resp.json()["platform"] == "other"


def test_unknown_platform_returns_404(client):
    resp = client.get("/api/conversion-tracking/guide/unknown")
    assert resp.status_code == 404
