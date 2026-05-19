from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from adcopilot.domain.entities import AccountId


class ConversionActionHealth(StrEnum):
    HEALTHY = "healthy"     # ENABLED + conversions > 0 last 7d
    STALE = "stale"         # ENABLED + conversions = 0 last 7d
    DISABLED = "disabled"   # REMOVED or HIDDEN
    MISSING = "missing"     # no conversion actions at all


@dataclass(frozen=True)
class ConversionActionStatus:
    action_id: int
    name: str
    status: str
    all_conversions: float
    health: ConversionActionHealth


@dataclass(frozen=True)
class ConversionAuditResult:
    account_id: AccountId
    action_statuses: list[ConversionActionStatus]
    diagnostic_message_pl: str
    overall_health: ConversionActionHealth
