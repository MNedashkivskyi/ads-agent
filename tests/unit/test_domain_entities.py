from datetime import UTC, datetime

import pytest

from adcopilot.domain.entities import (
    AccountId,
    GoogleAdsAccount,
    OAuthCredentials,
    PlanTier,
    User,
    UserId,
)


def make_user(**kwargs: object) -> User:
    defaults: dict[str, object] = {
        "id": UserId("user-1"),
        "email": "test@example.com",
        "telegram_chat_id": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "plan": PlanTier.STARTER,
    }
    defaults.update(kwargs)
    return User(**defaults)  # type: ignore[arg-type]


def make_account(**kwargs: object) -> GoogleAdsAccount:
    defaults: dict[str, object] = {
        "id": AccountId("acc-1"),
        "user_id": UserId("user-1"),
        "customer_id": "123-456-7890",
        "descriptive_name": "My Ads Account",
        "currency": "USD",
        "timezone": "America/New_York",
        "is_manager": False,
        "write_enabled": False,
        "connected_at": datetime(2026, 1, 2, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return GoogleAdsAccount(**defaults)  # type: ignore[arg-type]


def test_user_is_frozen() -> None:
    user = make_user()
    with pytest.raises((AttributeError, TypeError)):
        user.__dict__  # type: ignore[attr-defined]  # noqa: B018
        # Attempt mutation via dataclasses FrozenInstanceError
        import dataclasses

        dataclasses.fields(user)  # just verify it's a dataclass
        # Use setattr to trigger FrozenInstanceError
        user.email = "other@example.com"


def test_google_ads_account_is_frozen() -> None:
    import dataclasses

    account = make_account()
    assert any(f.name == "customer_id" for f in dataclasses.fields(account))
    with pytest.raises((AttributeError, TypeError)):
        account.customer_id = "999"


def test_oauth_credentials_is_frozen() -> None:
    creds = OAuthCredentials(
        account_id=AccountId("acc-1"),
        refresh_token="token",
        access_token=None,
        expires_at=None,
    )
    with pytest.raises((AttributeError, TypeError)):
        creds.refresh_token = "other"


def test_plan_tier_values() -> None:
    assert PlanTier.STARTER.value == "starter"
    assert PlanTier.GROWTH.value == "growth"
    assert PlanTier.PRO.value == "pro"


def test_user_id_and_account_id_are_strings() -> None:
    uid = UserId("abc")
    aid = AccountId("xyz")
    assert isinstance(uid, str)
    assert isinstance(aid, str)
