"""AdsPerformancePort — one interface, both tracks read through it.

The heart of the shared learning spine on the ingest side. A single nightly pull
returns three row types per account:

* **per-asset** rows (CTR / conversions / ``performance_label``) → attributed back
  to a creative ``angle``;
* **per-keyword** rows → attributed back to a keyword ``intent-type``;
* **search-term** rows (what people *actually typed*) → fuel the keyword
  harvesting loop and negative-keyword detection.

Return types are domain DTOs (plain dataclasses), never vendor payloads, so the
domain never imports the Google Ads SDK. Implementations live in
``infrastructure/`` and are fail-open / typed-error per the adapter contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class AssetPerformanceRow:
    """One ad asset's performance on one day.

    ``asset_id`` is the Google Ads asset id; ``field_type`` is the surface it was
    served in (HEADLINE / DESCRIPTION). ``performance_label`` is the raw Google
    Ads rating string (parsed downstream into ``PerformanceLabel``).
    """

    account_id: str
    customer_id: str
    day: date
    asset_id: str
    asset_text: str
    field_type: str
    ad_group_id: str
    campaign_id: str
    impressions: int
    clicks: int
    conversions: float
    cost_micros: int
    performance_label: str


@dataclass(frozen=True)
class KeywordPerformanceRow:
    """One keyword criterion's performance on one day."""

    account_id: str
    customer_id: str
    day: date
    criterion_id: str
    keyword_text: str
    match_type: str
    ad_group_id: str
    campaign_id: str
    impressions: int
    clicks: int
    conversions: float
    cost_micros: int


@dataclass(frozen=True)
class SearchTermRow:
    """One actual search query that triggered an ad on one day.

    ``status`` reflects whether the term is already ADDED as a keyword, EXCLUDED
    as a negative, or NONE (neither). ``matched_keyword_text`` is the keyword
    that triggered the ad, used to attribute the term to an intent-type.
    """

    account_id: str
    customer_id: str
    day: date
    search_term: str
    matched_keyword_text: str
    ad_group_id: str
    campaign_id: str
    impressions: int
    clicks: int
    conversions: float
    cost_micros: int
    status: str = "NONE"
    extra: dict = field(default_factory=dict)


class AdsPerformancePort(Protocol):
    """Read per-asset, per-keyword, and search-term performance for an account."""

    async def fetch_asset_performance(
        self,
        refresh_token: str,
        customer_id: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[AssetPerformanceRow]:
        """Per-asset rows over the date range. Never raises auth/SDK exceptions
        raw — surfaces a typed error or fails open per the adapter contract."""
        ...

    async def fetch_keyword_performance(
        self,
        refresh_token: str,
        customer_id: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[KeywordPerformanceRow]:
        """Per-keyword rows over the date range."""
        ...

    async def fetch_search_terms(
        self,
        refresh_token: str,
        customer_id: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[SearchTermRow]:
        """Search-term rows (actual queries) over the date range."""
        ...
