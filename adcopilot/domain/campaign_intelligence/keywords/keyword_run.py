"""KeywordRun — a keyword-generation/validation job for one campaign.

The pollable unit the API exposes: generate creates it, validate advances it. It
owns its candidates and tracks the status the client polls
(generating → generated → validating → ready, or failed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class KeywordRunStatus(StrEnum):
    GENERATING = "generating"
    GENERATED = "generated"
    VALIDATING = "validating"
    READY = "ready"
    FAILED = "failed"


@dataclass
class KeywordRun:
    """Metadata for one keyword run. Candidates are persisted separately."""

    campaign_id: str
    account_id: str
    user_id: str
    vertical: str
    language: str = "pl"
    service: str = ""
    problems: list[str] = field(default_factory=list)
    seeds: list[str] = field(default_factory=list)
    status: KeywordRunStatus = KeywordRunStatus.GENERATING
    error: str | None = None
    id: str | None = None
    created_at: datetime | None = None
