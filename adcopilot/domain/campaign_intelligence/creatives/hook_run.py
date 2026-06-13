"""HookRun — a hook-generation/selection/finalization job for one campaign."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class HookRunStatus(StrEnum):
    GENERATING = "generating"
    READY = "ready"
    FINALIZED = "finalized"
    FAILED = "failed"


@dataclass
class HookRun:
    campaign_id: str
    account_id: str
    user_id: str
    vertical: str
    language: str = "pl"
    service: str = ""
    problems: list[str] = field(default_factory=list)
    status: HookRunStatus = HookRunStatus.GENERATING
    rsa_payload: dict | None = None
    error: str | None = None
    id: str | None = None
    created_at: datetime | None = None
