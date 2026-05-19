"""Notification domain entity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType

NotificationId = NewType("NotificationId", str)


class NotificationType(StrEnum):
    DIGEST = "DIGEST"
    ALERT = "ALERT"
    EXECUTION_RESULT = "EXECUTION_RESULT"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    INSIGHT = "INSIGHT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class Notification:
    id: NotificationId
    user_id: str
    notification_type: NotificationType
    title: str
    body: str
    metadata: dict
    read_at: datetime | None
    created_at: datetime
