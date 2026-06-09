from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType

UserId = NewType("UserId", str)
AccountId = NewType("AccountId", str)


class PlanTier(StrEnum):
    STARTER = "starter"
    PROFESSIONAL = "professional"
    BUSINESS = "business"

    @classmethod
    def parse(cls, value: str | None) -> "PlanTier":
        """Tolerantly coerce a stored/inbound plan string to a PlanTier.

        Handles legacy slugs ("growth"/"pro" from before the vocabulary was
        unified) and any unknown/missing value by falling back to the most
        restrictive tier (STARTER). This keeps user loading from ever crashing
        on a stale ``users.plan`` value.
        """
        if not value:
            return cls.STARTER
        normalized = value.strip().lower()
        aliases = {
            "pro": cls.PROFESSIONAL,
            "growth": cls.PROFESSIONAL,
            "biz": cls.BUSINESS,
        }
        if normalized in aliases:
            return aliases[normalized]
        try:
            return cls(normalized)
        except ValueError:
            return cls.STARTER


@dataclass(frozen=True)
class User:
    id: UserId
    email: str
    telegram_chat_id: int | None
    created_at: datetime
    plan: PlanTier
    notifications_paused: bool = False
    password_hash: str | None = None
    notification_hour: int = 9
    language: str = "pl"
    stripe_customer_id: str | None = None
    subscription_status: str = "trialing"
    trial_ends_at: datetime | None = None
    trial_started_at: datetime | None = None
    subscription_id: str | None = None


@dataclass(frozen=True)
class GoogleAdsAccount:
    id: AccountId
    user_id: UserId
    customer_id: str
    descriptive_name: str
    currency: str
    timezone: str
    is_manager: bool
    write_enabled: bool
    connected_at: datetime
    needs_reauth: bool = False
    # Polish-market vertical (e.g. "salon", "prawnik"), populated by the vertical
    # classifier after the first snapshot. Drives the conversion-attribution
    # window used by lag-sensitive detection rules. None until classified.
    vertical: str | None = None


@dataclass(frozen=True)
class OAuthCredentials:
    account_id: AccountId
    refresh_token: str
    access_token: str | None
    expires_at: datetime | None
