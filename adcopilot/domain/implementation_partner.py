"""Domain model for implementation partners and requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import NewType

ImplementationPartnerId = NewType("ImplementationPartnerId", str)
ImplementationRequestId = NewType("ImplementationRequestId", str)


class ImplementationRequestStatus(Enum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class ImplementationPartner:
    id: ImplementationPartnerId
    name: str
    email: str
    website: str | None
    city: str
    voivodeship: str
    platforms_supported: list[str]
    fixed_price_pln: int
    avg_turnaround_hours: int
    rating: float
    completed_jobs: int
    is_active: bool


@dataclass
class ImplementationRequest:
    id: ImplementationRequestId
    client_id: str
    partner_id: str
    account_id: str
    status: ImplementationRequestStatus
    platform: str
    created_at: datetime
    accepted_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
