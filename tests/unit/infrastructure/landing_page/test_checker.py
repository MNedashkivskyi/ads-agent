"""Unit tests for LandingPageChecker."""
from __future__ import annotations

import pytest
import httpx
import respx

from adcopilot.infrastructure.landing_page.checker import LandingPageChecker, LandingPageCheckResult


SAMPLE_HTML = """<!DOCTYPE html>
<html lang="pl">
<head><title>Kancelaria prawna Warszawa</title></head>
<body>
<h1>Profesjonalna obsługa prawna</h1>
<p>Oferujemy usługi prawne dla firm i osób prywatnych w Warszawie.</p>
</body>
</html>"""


@pytest.mark.asyncio
@respx.mock
async def test_check_returns_content_on_200():
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text=SAMPLE_HTML)
    )
    checker = LandingPageChecker()
    result = await checker.check("https://example.com/")

    assert result.reachable is True
    assert result.https is True
    assert result.page_title == "Kancelaria prawna Warszawa"
    assert result.h1_text == "Profesjonalna obsługa prawna"
    assert "prawne" in result.body_text_sample
    assert result.language_detected == "pl"
    assert result.error_message is None


@pytest.mark.asyncio
@respx.mock
async def test_check_non_200_returns_unreachable():
    respx.get("https://example.com/404").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    checker = LandingPageChecker()
    result = await checker.check("https://example.com/404")

    assert result.reachable is False
    assert "404" in result.error_message


@pytest.mark.asyncio
@respx.mock
async def test_check_timeout_returns_unreachable():
    respx.get("https://slow.example.com/").mock(side_effect=httpx.TimeoutException("timeout"))
    checker = LandingPageChecker()
    result = await checker.check("https://slow.example.com/")

    assert result.reachable is False
    assert result.error_message == "timeout"


@pytest.mark.asyncio
@respx.mock
async def test_check_http_url_sets_https_false():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(200, text=SAMPLE_HTML)
    )
    checker = LandingPageChecker()
    result = await checker.check("http://example.com/")

    assert result.https is False


@pytest.mark.asyncio
@respx.mock
async def test_check_connection_error_returns_unreachable():
    respx.get("https://bad.example.com/").mock(side_effect=httpx.ConnectError("refused"))
    checker = LandingPageChecker()
    result = await checker.check("https://bad.example.com/")

    assert result.reachable is False
    assert result.error_message is not None
