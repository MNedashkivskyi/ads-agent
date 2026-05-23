"""Unit tests for PageSpeedAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adcopilot.domain.exceptions import PageAnalyzerError
from adcopilot.infrastructure.landing_page.pagespeed_adapter import (
    PageSpeedAdapter,
    _parse_score,
    _safe_int,
)


def _make_psi_response(
    perf: float = 0.85, acc: float = 0.9, seo: float = 0.95, bp: float = 0.8
) -> dict:
    return {
        "id": "https://example.com/",
        "loadingExperience": {"overall_category": "FAST"},
        "lighthouseResult": {
            "categories": {
                "performance": {"score": perf},
                "accessibility": {"score": acc},
                "seo": {"score": seo},
                "best-practices": {"score": bp},
            },
            "audits": {
                "largest-contentful-paint": {"numericValue": 2500.0, "displayValue": "2.5 s"},
                "first-contentful-paint": {"numericValue": 1200.0},
                "cumulative-layout-shift": {"numericValue": 0.05},
                "server-response-time": {"numericValue": 180.0},
                "total-blocking-time": {"numericValue": 120.0},
                "speed-index": {"numericValue": 3100.0},
            },
        },
    }


def test_safe_int_clamps_to_0_100() -> None:
    assert _safe_int(0.0) == 0
    assert _safe_int(1.0) == 100
    assert _safe_int(0.85) == 85
    assert _safe_int(None) == 0


def test_parse_score_extracts_scores() -> None:
    score = _parse_score(_make_psi_response())
    assert score.performance_score == 85
    assert score.accessibility_score == 90
    assert score.seo_score == 95
    assert score.best_practices_score == 80
    assert score.mobile_friendly is True
    assert score.url == "https://example.com/"


def test_parse_score_core_web_vitals() -> None:
    score = _parse_score(_make_psi_response())
    assert score.core_web_vitals.lcp_ms == 2500.0
    assert score.core_web_vitals.fcp_ms == 1200.0
    assert score.core_web_vitals.cls_score == 0.05
    assert score.core_web_vitals.tbt_ms == 120.0


def test_parse_score_mobile_unfriendly_when_slow() -> None:
    data = _make_psi_response()
    data["loadingExperience"]["overall_category"] = "SLOW"
    score = _parse_score(data)
    assert score.mobile_friendly is False


def test_parse_score_recommendations_empty() -> None:
    score = _parse_score(_make_psi_response())
    assert score.recommendations_pl == []


@pytest.mark.asyncio
async def test_analyze_returns_score() -> None:
    adapter = PageSpeedAdapter(api_key="test-key")
    mock_response = MagicMock()
    mock_response.json.return_value = _make_psi_response()
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        score = await adapter.analyze("https://example.com")

    assert score.performance_score == 85


@pytest.mark.asyncio
async def test_analyze_raises_on_timeout() -> None:
    import httpx as _httpx

    adapter = PageSpeedAdapter()
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=_httpx.TimeoutException("timeout"))
        mock_client_class.return_value = mock_client

        with pytest.raises(PageAnalyzerError, match="timeout"):
            await adapter.analyze("https://slow.example.com")
