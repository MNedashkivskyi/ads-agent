"""HTTP website crawler adapter using httpx + stdlib html.parser."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
import structlog

from adcopilot.domain.launch.website_intelligence import CrawlStatus, WebsiteIntelligence

logger = structlog.get_logger(__name__)

_TIMEOUT = 10.0
_USER_AGENT = "AdeptBot/1.0 (+https://adwise.app/bot)"
_MAX_LINKED_PAGES = 3
_PHONE_REGEX = re.compile(
    r"(?:(?:\+48|0048)?[\s\-]?)?"
    r"(?:\d{3}[\s\-]\d{3}[\s\-]\d{3}"
    r"|\d{2}[\s\-]\d{3}[\s\-]\d{2}[\s\-]\d{2}"
    r"|\d{9,11})",
)
_POLISH_PATTERNS = re.compile(
    r"\b(ul\.|ulica|aleja|pl\.|plac|os\.|osiedle|warszawa|kraków|wrocław|gdańsk|poznań|łódź"
    r"|śląski|mazowieckie|małopolskie|dolnośląskie)\b",
    re.IGNORECASE,
)
_SERVICE_KEYWORDS_PL = re.compile(
    r"\b(manicure|pedicure|masaż|fryzjer|stomatolog|dentysta|adwokat|prawnik"
    r"|sprzątanie|naprawa|serwis|kancelaria|restauracja|catering|warsztat)\b",
    re.IGNORECASE,
)


class _PageParser(HTMLParser):
    """Minimal HTML parser that extracts text content, meta tags, and JSON-LD."""

    def __init__(self) -> None:
        super().__init__()
        self._text_parts: list[str] = []
        self._in_script = False
        self._in_style = False
        self._script_type = ""
        self._script_buffer = ""
        self.meta_description = ""
        self.og_title = ""
        self.og_description = ""
        self.title = ""
        self._in_title = False
        self.schema_org: dict | None = None
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        if tag == "script":
            self._in_script = True
            self._script_type = attr_dict.get("type", "")
            self._script_buffer = ""
        elif tag == "style":
            self._in_style = True
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (attr_dict.get("name") or "").lower()
            prop = (attr_dict.get("property") or "").lower()
            content = attr_dict.get("content") or ""
            if name == "description":
                self.meta_description = content
            elif prop == "og:title":
                self.og_title = content
            elif prop == "og:description":
                self.og_description = content
        elif tag == "a":
            href = attr_dict.get("href") or ""
            if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            if "application/ld+json" in self._script_type and not self.schema_org:
                try:
                    self.schema_org = json.loads(self._script_buffer)
                except (json.JSONDecodeError, ValueError):
                    pass
            self._in_script = False
            self._script_type = ""
        elif tag == "style":
            self._in_style = False
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_buffer += data
        elif self._in_style:
            pass
        elif self._in_title:
            self.title += data
        else:
            stripped = data.strip()
            if stripped:
                self._text_parts.append(stripped)

    @property
    def text(self) -> str:
        return " ".join(self._text_parts)


def _extract_phones(text: str) -> list[str]:
    raw = _PHONE_REGEX.findall(text)
    seen: set[str] = set()
    result: list[str] = []
    for m in raw:
        digits = re.sub(r"\D", "", m)
        if 9 <= len(digits) <= 12 and digits not in seen:
            seen.add(digits)
            result.append(m.strip())
    return result[:3]


def _detect_language(text: str) -> str:
    if _POLISH_PATTERNS.search(text):
        return "pl"
    polish_chars = sum(text.count(c) for c in "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
    return "pl" if polish_chars > 5 else "other"


def _extract_schema_data(
    schema: dict | list | None,
) -> tuple[str, str, str]:
    """Return (business_name, address, phone) from Schema.org data."""
    if schema is None:
        return "", "", ""
    if isinstance(schema, list):
        for item in schema:
            n, a, p = _extract_schema_data(item)
            if n or a or p:
                return n, a, p
        return "", "", ""
    stype = schema.get("@type", "")
    if isinstance(stype, list):
        is_business = any(
            t in ("LocalBusiness", "Organization", "MedicalBusiness", "LegalService") for t in stype
        )
    else:
        is_business = stype in ("LocalBusiness", "Organization", "MedicalBusiness", "LegalService")
    if not is_business:
        return "", "", ""
    name = schema.get("name", "")
    phone = schema.get("telephone", "")
    address = schema.get("address", {})
    if isinstance(address, dict):
        city = address.get("addressLocality", "")
        street = address.get("streetAddress", "")
        # Put city first so `city` property extracts it correctly
        addr_str = ", ".join(filter(None, [city, street]))
    else:
        addr_str = str(address)
    return name, addr_str, phone


def _pick_subpages(base_url: str, links: list[str]) -> list[str]:
    """Pick up to _MAX_LINKED_PAGES subpages likely to have business info."""
    parsed = urlparse(base_url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"
    priority_patterns = re.compile(
        r"(kontakt|contact|o-nas|about|uslugi|services|cennik|pricing|oferta|offer)",
        re.IGNORECASE,
    )
    candidates: list[str] = []
    for link in links:
        full = urljoin(base_domain, link) if link.startswith("/") else link
        if not full.startswith(base_domain):
            continue
        if priority_patterns.search(full):
            candidates.append(full)
    return list(dict.fromkeys(candidates))[:_MAX_LINKED_PAGES]


def _is_robots_blocked(robots_txt: str, user_agent: str) -> bool:
    """Very lightweight robots.txt check."""
    lines = robots_txt.lower().splitlines()
    applicable = False
    for line in lines:
        line = line.strip()
        if line.startswith("user-agent:"):
            ua = line.split(":", 1)[1].strip()
            applicable = ua in ("*", user_agent.lower().split("/")[0])
        elif applicable and line.startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path in ("/", ""):
                return True
    return False


class HttpWebsiteCrawlerAdapter:
    """Fetches homepage + contact/about/services pages and extracts business data."""

    async def crawl(self, url: str) -> WebsiteIntelligence:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        headers = {"User-Agent": _USER_AGENT, "Accept-Language": "pl,en;q=0.8"}

        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers=headers,
        ) as client:
            # Check robots.txt
            try:
                robots_resp = await client.get(f"{base}/robots.txt")
                if robots_resp.status_code == 200 and _is_robots_blocked(
                    robots_resp.text, _USER_AGENT
                ):
                    logger.info("website_crawler: robots blocked", url=url)
                    return WebsiteIntelligence(url=url, crawl_status=CrawlStatus.ROBOTS_BLOCKED)
            except Exception:
                pass  # robots.txt missing or unreachable — continue

            # Fetch homepage
            try:
                resp = await client.get(url)
                if resp.status_code >= 400:
                    return WebsiteIntelligence(url=url, crawl_status=CrawlStatus.FAILED)
                home_html = resp.text
            except httpx.TimeoutException:
                return WebsiteIntelligence(url=url, crawl_status=CrawlStatus.TIMEOUT)
            except Exception as exc:
                logger.info("website_crawler: fetch failed", url=url, error=str(exc))
                return WebsiteIntelligence(url=url, crawl_status=CrawlStatus.FAILED)

            parser = _PageParser()
            parser.feed(home_html)

            all_text = parser.text
            subpages = _pick_subpages(url, parser.links)

            # Fetch subpages
            for sub_url in subpages:
                try:
                    sub_resp = await client.get(sub_url)
                    if sub_resp.status_code < 400:
                        sub_parser = _PageParser()
                        sub_parser.feed(sub_resp.text)
                        all_text += " " + sub_parser.text
                        if not parser.schema_org and sub_parser.schema_org:
                            parser.schema_org = sub_parser.schema_org
                except Exception:
                    continue

        # Extract structured data
        schema_name, schema_addr, schema_phone = _extract_schema_data(parser.schema_org)
        phones = _extract_phones(all_text)
        if schema_phone and schema_phone not in phones:
            phones.insert(0, schema_phone)

        services = list(dict.fromkeys(_SERVICE_KEYWORDS_PL.findall(all_text)))[:10]

        business_name = schema_name or parser.og_title or parser.title.strip()
        location_text = schema_addr

        lang = _detect_language(all_text)

        logger.info(
            "website_crawler: crawl complete",
            url=url,
            phones=len(phones),
            services=len(services),
            has_schema=parser.schema_org is not None,
        )

        return WebsiteIntelligence(
            url=url,
            crawl_status=CrawlStatus.OK,
            business_name=business_name,
            location_text=location_text,
            phone_numbers=phones,
            services_detected=services,
            language=lang,
            meta_description=parser.meta_description,
            og_title=parser.og_title,
            schema_org_data=parser.schema_org,
        )
