"""Organization / membership domain (team seats, Phase 3 / T3.4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MembershipRole(StrEnum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"

    @classmethod
    def parse(cls, value: str | None) -> "MembershipRole":
        if not value:
            return cls.MEMBER
        try:
            return cls(value.strip().upper())
        except ValueError:
            return cls.MEMBER


@dataclass(frozen=True)
class Organization:
    id: str
    name: str
    owner_user_id: str
    is_personal: bool
    created_at: datetime


@dataclass(frozen=True)
class Membership:
    id: str
    organization_id: str
    user_id: str
    role: MembershipRole
    created_at: datetime


@dataclass(frozen=True)
class OrganizationInvitation:
    id: str
    organization_id: str
    email: str
    role: MembershipRole
    token: str
    accepted_at: datetime | None
    created_at: datetime

    @property
    def is_pending(self) -> bool:
        return self.accepted_at is None
