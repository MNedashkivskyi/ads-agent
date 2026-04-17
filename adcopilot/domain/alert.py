"""Alert domain model — high-priority real-time anomaly notifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, NewType

from adcopilot.domain.entities import AccountId

AlertId = NewType("AlertId", str)


class AlertKind(Enum):
    SPEND_SPIKE = "SPEND_SPIKE"
    CONVERSION_DROUGHT = "CONVERSION_DROUGHT"
    BUDGET_BURNING_FAST = "BUDGET_BURNING_FAST"
    TRACKING_ERROR = "TRACKING_ERROR"
    IMPRESSION_SHARE_DROP = "IMPRESSION_SHARE_DROP"


class AlertSeverity(Enum):
    CRITICAL = "CRITICAL"


class AlertStatus(Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    SUPPRESSED = "SUPPRESSED"  # rate-limit suppression


@dataclass(frozen=True)
class Alert:
    """A real-time anomaly alert for a Google Ads account.

    Alerts are created by AnomalyDetectionUseCase and are distinct from
    Recommendations: they require immediate attention, always carry
    CRITICAL severity, and are rate-limited to 3 per account per 24 hours.
    """

    id: AlertId
    account_id: AccountId
    kind: AlertKind
    severity: AlertSeverity
    status: AlertStatus
    payload: dict[str, Any]
    message: str
    created_at: datetime
