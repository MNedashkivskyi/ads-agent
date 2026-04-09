"""
Tests using in-memory fake repository implementations to verify the port contracts.
"""

from datetime import UTC, datetime

import pytest

from adcopilot.application.ports.repositories import (
    GoogleAdsAccountRepository,
    OAuthCredentialsRepository,
    UserRepository,
)
from adcopilot.domain.entities import (
    AccountId,
    GoogleAdsAccount,
    OAuthCredentials,
    PlanTier,
    User,
    UserId,
)

# ---------------------------------------------------------------------------
# In-memory fake implementations
# ---------------------------------------------------------------------------


class FakeUserRepository:
    def __init__(self) -> None:
        self._store: dict[UserId, User] = {}

    async def get_by_id(self, user_id: UserId) -> User | None:
        return self._store.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._store.values() if u.email == email), None)

    async def save(self, user: User) -> User:
        self._store[user.id] = user
        return user


class FakeGoogleAdsAccountRepository:
    def __init__(self) -> None:
        self._store: dict[AccountId, GoogleAdsAccount] = {}

    async def get(self, account_id: AccountId) -> GoogleAdsAccount | None:
        return self._store.get(account_id)

    async def list_for_user(self, user_id: UserId) -> list[GoogleAdsAccount]:
        return [a for a in self._store.values() if a.user_id == user_id]

    async def save(self, account: GoogleAdsAccount) -> GoogleAdsAccount:
        self._store[account.id] = account
        return account


class FakeOAuthCredentialsRepository:
    def __init__(self) -> None:
        self._store: dict[AccountId, OAuthCredentials] = {}

    async def get(self, account_id: AccountId) -> OAuthCredentials | None:
        return self._store.get(account_id)

    async def save(self, credentials: OAuthCredentials) -> OAuthCredentials:
        self._store[credentials.account_id] = credentials
        return credentials


# ---------------------------------------------------------------------------
# Verify fakes satisfy the Protocol
# ---------------------------------------------------------------------------


def _assert_implements_user_repo(repo: UserRepository) -> None:
    pass


def _assert_implements_ads_account_repo(repo: GoogleAdsAccountRepository) -> None:
    pass


def _assert_implements_oauth_repo(repo: OAuthCredentialsRepository) -> None:
    pass


def test_fake_repos_satisfy_protocols() -> None:
    _assert_implements_user_repo(FakeUserRepository())
    _assert_implements_ads_account_repo(FakeGoogleAdsAccountRepository())
    _assert_implements_oauth_repo(FakeOAuthCredentialsRepository())


# ---------------------------------------------------------------------------
# Behaviour tests
# ---------------------------------------------------------------------------


@pytest.fixture
def user_repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def account_repo() -> FakeGoogleAdsAccountRepository:
    return FakeGoogleAdsAccountRepository()


@pytest.fixture
def oauth_repo() -> FakeOAuthCredentialsRepository:
    return FakeOAuthCredentialsRepository()


async def test_save_and_get_user_by_id(user_repo: FakeUserRepository) -> None:
    user = User(
        id=UserId("u1"),
        email="alice@example.com",
        telegram_chat_id=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        plan=PlanTier.STARTER,
    )
    await user_repo.save(user)
    fetched = await user_repo.get_by_id(UserId("u1"))
    assert fetched == user


async def test_get_user_by_email(user_repo: FakeUserRepository) -> None:
    user = User(
        id=UserId("u2"),
        email="bob@example.com",
        telegram_chat_id=12345,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        plan=PlanTier.GROWTH,
    )
    await user_repo.save(user)
    fetched = await user_repo.get_by_email("bob@example.com")
    assert fetched == user


async def test_get_nonexistent_user_returns_none(user_repo: FakeUserRepository) -> None:
    result = await user_repo.get_by_id(UserId("doesnotexist"))
    assert result is None


async def test_save_and_list_accounts_for_user(
    account_repo: FakeGoogleAdsAccountRepository,
) -> None:
    acc1 = GoogleAdsAccount(
        id=AccountId("a1"),
        user_id=UserId("u1"),
        customer_id="111",
        descriptive_name="Acme Corp",
        currency="USD",
        timezone="UTC",
        is_manager=False,
        write_enabled=True,
        connected_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    acc2 = GoogleAdsAccount(
        id=AccountId("a2"),
        user_id=UserId("u2"),
        customer_id="222",
        descriptive_name="Other",
        currency="EUR",
        timezone="UTC",
        is_manager=False,
        write_enabled=False,
        connected_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    await account_repo.save(acc1)
    await account_repo.save(acc2)

    accounts = await account_repo.list_for_user(UserId("u1"))
    assert len(accounts) == 1
    assert accounts[0] == acc1


async def test_oauth_save_and_get(oauth_repo: FakeOAuthCredentialsRepository) -> None:
    creds = OAuthCredentials(
        account_id=AccountId("a1"),
        refresh_token="secret-token",
        access_token="access-token",
        expires_at=None,
    )
    await oauth_repo.save(creds)
    fetched = await oauth_repo.get(AccountId("a1"))
    assert fetched == creds
