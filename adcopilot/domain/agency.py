"""Agency prospecting domain (Phase 5C).

A Prospect is a client account discovered under an agency's Google Ads manager
(MCC) that the agency audits and tracks toward becoming a managed client. No
auto-convert in v1 — status is tracked; onboarding reuses the existing flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ProspectStatus(StrEnum):
    NEW = "new"  # discovered under the MCC, not yet audited
    AUDITED = "audited"  # a waste report has been computed
    CONTACTED = "contacted"  # the agency reached out
    WON = "won"  # became a managed client
    LOST = "lost"


@dataclass(frozen=True)
class Prospect:
    id: str
    organization_id: str
    customer_id: str  # the prospect's (child) Google Ads customer id
    name: str
    status: ProspectStatus = ProspectStatus.NEW
    mcc_customer_id: str | None = None
    audit_session_id: str | None = None
    report_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
