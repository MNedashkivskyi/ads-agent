"""Unit tests for HttpWebsiteCrawlerAdapter (Task 3.1)."""

from __future__ import annotations

import pytest
import respx
import httpx

from adcopilot.domain.launch.website_intelligence import CrawlStatus
from adcopilot.infrastructure.adapters.http_website_crawler import HttpWebsiteCrawlerAdapter


SCHEMA_ORG_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Salon Urody Marta</title>
  <meta name="description" content="Profesjonalny salon urody w Krakowie">
  <script type="application/ld+json">
  {
    "@type": "LocalBusiness",
    "name": "Salon Urody Marta",
    "telephone": "+48 123 456 789",
    "address": {
      "@type": "PostalAddress",
      "streetAddress": "ul. Floriańska 5",
      "addressLocality": "Kraków"
    }
  }
  </script>
</head>
<body>
  <h1>Salon Urody Marta</h1>
  <p>Oferujemy manicure, pedicure i masaż. Zapraszamy do Krakowa!</p>
  <a href="/kontakt">Kontakt</a>
</body>
</html>"""

PLAIN_HTML = """<!DOCTYPE html>
<html>
<head><title>Warsztat Kowalski</title></head>
<body>
  <p>Naprawa samochodów w Warszawie. Telefon: 600 700 800</p>
  <p>ul. Puławska 10, Warszawa</p>
</body>
</html>"""

ROBOTS_TXT = "User-agent: *\nDisallow: /"


@pytest.mark.asyncio
@respx.mock
async def test_schema_org_extraction():
    respx.get("https://example.pl/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.pl/").mock(return_value=httpx.Response(200, text=SCHEMA_ORG_HTML))

    adapter = HttpWebsiteCrawlerAdapter()
    result = await adapter.crawl("https://example.pl/")

    assert result.crawl_status == CrawlStatus.OK
    assert "Salon Urody Marta" in result.business_name
    assert result.city == "Kraków"
    assert any("123" in p for p in result.phone_numbers)
    assert result.schema_org_data is not None


@pytest.mark.asyncio
@respx.mock
async def test_plain_html_extraction():
    respx.get("https://warsztat.pl/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://warsztat.pl/").mock(return_value=httpx.Response(200, text=PLAIN_HTML))

    adapter = HttpWebsiteCrawlerAdapter()
    result = await adapter.crawl("https://warsztat.pl/")

    assert result.crawl_status == CrawlStatus.OK
    assert any("600" in p or "700" in p for p in result.phone_numbers)
    assert result.language == "pl"


@pytest.mark.asyncio
@respx.mock
async def test_broken_site_returns_failed():
    respx.get("https://broken.pl/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://broken.pl/").mock(return_value=httpx.Response(503))

    adapter = HttpWebsiteCrawlerAdapter()
    result = await adapter.crawl("https://broken.pl/")

    assert result.crawl_status == CrawlStatus.FAILED


@pytest.mark.asyncio
@respx.mock
async def test_timeout_returns_timeout_status():
    respx.get("https://slow.pl/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://slow.pl/").mock(side_effect=httpx.TimeoutException("timeout"))

    adapter = HttpWebsiteCrawlerAdapter()
    result = await adapter.crawl("https://slow.pl/")

    assert result.crawl_status == CrawlStatus.TIMEOUT


@pytest.mark.asyncio
@respx.mock
async def test_robots_blocked():
    respx.get("https://blocked.pl/robots.txt").mock(
        return_value=httpx.Response(200, text=ROBOTS_TXT)
    )

    adapter = HttpWebsiteCrawlerAdapter()
    result = await adapter.crawl("https://blocked.pl/")

    assert result.crawl_status == CrawlStatus.ROBOTS_BLOCKED
