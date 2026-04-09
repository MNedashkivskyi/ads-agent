from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType

UserId = NewType("UserId", str)
AccountId = NewType("AccountId", str)


class PlanTier(StrEnum):
    STARTER = "starter"
    GROWTH = "growth"
    PRO = "pro"


@dataclass(frozen=True)
class User:
    id: UserId
    email: str
    telegram_chat_id: int | None
    created_at: datetime
    plan: PlanTier


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


@dataclass(frozen=True)
class OAuthCredentials:
    account_id: AccountId
    refresh_token: str
    access_token: str | None
    expires_at: datetime | None
