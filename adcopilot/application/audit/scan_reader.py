"""Read-only Google Ads reader for the free audit (Audit Funnel Phase 2 / T2.1).

The nightly snapshot port (``GoogleAdsClientPort``) reads one *day* at a time;
an audit needs a 30-day *aggregate*. This narrow port expresses exactly what the
scan needs — accessible customers and one windowed pull — so the orchestration
(``RunAuditScanUseCase``) can be unit-tested against a fake, while the live
GAQL implementation stays a thin, separately-verified adapter.

All reads are read-only by policy: the audit never dispatches mutations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adcopilot.domain.snapshot import (
    CampaignSnapshot,
    ConversionActionSnapshot,
    KeywordSnapshot,
    SearchTermSnapshot,
)


@dataclass(frozen=True)
class AuditRawData:
    """The windowed, read-only pull the engine's dataset is built from."""

    campaigns: list[CampaignSnapshot]
    search_terms: list[SearchTermSnapshot]
    keywords: list[KeywordSnapshot]
    conversion_actions: list[ConversionActionSnapshot]


class AuditScanReader(Protocol):
    async def accessible_customers(self, refresh_token: str) -> list[str]: ...

    async def pull(self, refresh_token: str, customer_id: str, days: int) -> AuditRawData: ...
