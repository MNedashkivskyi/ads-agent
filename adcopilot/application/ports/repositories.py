from typing import Protocol

from adcopilot.domain.entities import (
    AccountId,
    GoogleAdsAccount,
    OAuthCredentials,
    User,
    UserId,
)


class UserRepository(Protocol):
    async def get_by_id(self, user_id: UserId) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...

    async def save(self, user: User) -> User: ...


class GoogleAdsAccountRepository(Protocol):
    async def get(self, account_id: AccountId) -> GoogleAdsAccount | None: ...

    async def list_for_user(self, user_id: UserId) -> list[GoogleAdsAccount]: ...

    async def save(self, account: GoogleAdsAccount) -> GoogleAdsAccount: ...


class OAuthCredentialsRepository(Protocol):
    async def get(self, account_id: AccountId) -> OAuthCredentials | None: ...

    async def save(self, credentials: OAuthCredentials) -> OAuthCredentials: ...
