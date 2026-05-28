"""Domain entity for extracted website intelligence."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CrawlStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ROBOTS_BLOCKED = "robots_blocked"


class WebsiteIntelligence(BaseModel):
    """Structured information extracted from a business website."""

    model_config = {"frozen": True}

    url: str
    crawl_status: CrawlStatus = CrawlStatus.OK

    business_name: str = ""
    location_text: str = ""
    phone_numbers: list[str] = Field(default_factory=list)
    services_detected: list[str] = Field(default_factory=list)
    language: str = "pl"

    meta_description: str = ""
    og_title: str = ""
    schema_org_data: dict[str, Any] | None = None

    @property
    def is_successful(self) -> bool:
        return self.crawl_status == CrawlStatus.OK

    @property
    def primary_phone(self) -> str | None:
        return self.phone_numbers[0] if self.phone_numbers else None

    @property
    def city(self) -> str:
        """Best-effort city extraction from location_text."""
        if not self.location_text:
            return ""
        # Take the part before the first comma (e.g. "Kraków, małopolskie" → "Kraków")
        return self.location_text.split(",")[0].strip()
