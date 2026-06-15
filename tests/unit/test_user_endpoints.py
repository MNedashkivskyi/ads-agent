"""Tests for user endpoints — response models, plan limits, CORS, entity fields.

Pure unit tests that don't touch a real database or external services.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from adcopilot.application.entitlements import max_accounts as plan_max_accounts
from adcopilot.domain.entities import GoogleAdsAccount, PlanTier, User, UserId
from adcopilot.interfaces.api.users import UserMeResponse

_USER_ID = str(uuid.uuid4())
_ACCOUNT_ID = str(uuid.uuid4())
_NOW = datetime.now(UTC)


def _make_user(
    user_id: str = _USER_ID,
    plan: PlanTier = PlanTier.STARTER,
    trial_started_at: datetime | None = None,
    subscription_status: str = "trialing",
) -> User:
    return User(
        id=UserId(user_id),
        email="test@example.com",
        telegram_chat_id=None,
        created_at=_NOW,
        plan=plan,
        trial_started_at=trial_started_at,
        subscription_status=subscription_status,
    )


# ---------------------------------------------------------------------------
# UserMeResponse — new fields present
# ---------------------------------------------------------------------------


class TestUserMeResponse:
    """Verify the Pydantic model has all required fields."""

    def test_includes_plan_field(self) -> None:
        assert "plan" in UserMeResponse.model_fields

    def test_includes_max_accounts_field(self) -> None:
        assert "max_accounts" in UserMeResponse.model_fields

    def test_includes_subscription_status_field(self) -> None:
        assert "subscription_status" in UserMeResponse.model_fields

    def test_includes_trial_started_at_field(self) -> None:
        assert "trial_started_at" in UserMeResponse.model_fields

    def test_serialises_with_all_fields(self) -> None:
        resp = UserMeResponse(
            user_id=_USER_ID,
            email="test@example.com",
            telegram_chat_id=None,
            role="client",
            plan="starter",
            max_accounts=1,
            subscription_status="trialing",
            trial_started_at=None,
        )
        data = resp.model_dump()
        assert data["plan"] == "starter"
        assert data["max_accounts"] == 1
        assert data["subscription_status"] == "trialing"
        assert data["trial_started_at"] is None

    def test_serialises_with_trial_started_at(self) -> None:
        ts = "2026-05-24T12:00:00+00:00"
        resp = UserMeResponse(
            user_id=_USER_ID,
            email="test@example.com",
            telegram_chat_id=None,
            role="client",
            plan="business",
            max_accounts=3,
            subscription_status="trialing",
            trial_started_at=ts,
        )
        assert resp.trial_started_at == ts


# ---------------------------------------------------------------------------
# Plan → max_accounts mapping
# ---------------------------------------------------------------------------


class TestPlanMaxAccounts:
    """New limits sourced from the central entitlements module:
    Starter 1 / Professional 3 / Business unlimited (None)."""

    def test_starter_allows_1(self) -> None:
        assert plan_max_accounts(PlanTier.STARTER) == 1

    def test_professional_allows_3(self) -> None:
        assert plan_max_accounts(PlanTier.PROFESSIONAL) == 3

    def test_business_is_unlimited(self) -> None:
        assert plan_max_accounts(PlanTier.BUSINESS) is None

    def test_unknown_plan_defaults_to_starter(self) -> None:
        # PlanTier.parse collapses unknown values to STARTER (limit 1).
        assert plan_max_accounts(PlanTier.parse("unknown")) == 1

    def test_all_plan_tiers_have_mapping(self) -> None:
        for tier in PlanTier:
            # None is a valid (unlimited) value, so assert the call succeeds.
            assert plan_max_accounts(tier) is None or plan_max_accounts(tier) >= 1


# ---------------------------------------------------------------------------
# CORS — Railway frontend origin
# ---------------------------------------------------------------------------


class TestCorsRailwayOrigin:
    def test_railway_origin_in_dev_origins(self) -> None:
        from adcopilot.config import Settings
        from adcopilot.security.cors import build_cors_allowed_origins

        settings = Settings(ENV="dev")
        origins = build_cors_allowed_origins(settings)
        assert "https://approve-ads-bot-dev.up.railway.app" in origins

    def test_railway_origin_not_in_production(self) -> None:
        from adcopilot.config import Settings
        from adcopilot.security.cors import build_cors_allowed_origins

        settings = Settings(ENV="production", APP_URL="https://adswise.xyz")
        origins = build_cors_allowed_origins(settings)
        assert "https://approve-ads-bot-dev.up.railway.app" not in origins

    def test_lovable_preview_would_need_app_url(self) -> None:
        """Lovable preview URL can be added via APP_URL in non-prod."""
        from adcopilot.config import Settings
        from adcopilot.security.cors import build_cors_allowed_origins

        lovable_url = "https://some-preview.lovableproject.com"
        settings = Settings(ENV="staging", APP_URL=lovable_url)
        origins = build_cors_allowed_origins(settings)
        assert lovable_url in origins


# ---------------------------------------------------------------------------
# Domain entity — trial_started_at
# ---------------------------------------------------------------------------


class TestUserEntity:
    def test_trial_started_at_defaults_to_none(self) -> None:
        user = _make_user()
        assert user.trial_started_at is None

    def test_trial_started_at_preserved(self) -> None:
        now = datetime.now(UTC)
        user = _make_user(trial_started_at=now)
        assert user.trial_started_at == now

    def test_subscription_status_defaults_to_trialing(self) -> None:
        user = _make_user()
        assert user.subscription_status == "trialing"


# ---------------------------------------------------------------------------
# OAuth start — quota limits match users module
# ---------------------------------------------------------------------------


class TestOAuthStartQuota:
    """The OAuth, users, and worker enforcement points now share one source
    of truth (the entitlements module), so there is no second map to drift."""

    def test_no_duplicate_limit_map_in_oauth(self) -> None:
        import adcopilot.interfaces.api.oauth as oauth_mod

        assert not hasattr(oauth_mod, "_PLAN_ACCOUNT_LIMITS")

    def test_no_duplicate_limit_map_in_worker(self) -> None:
        import adcopilot.interfaces.worker.tasks as tasks_mod

        assert not hasattr(tasks_mod, "_PLAN_ACCOUNT_LIMITS")

    def test_no_duplicate_limit_map_in_users(self) -> None:
        import adcopilot.interfaces.api.users as users_mod

        assert not hasattr(users_mod, "PLAN_MAX_ACCOUNTS")

    def test_limits_match_product_rules(self) -> None:
        # Starter 1, Professional 3, Business unlimited.
        assert plan_max_accounts(PlanTier.STARTER) == 1
        assert plan_max_accounts(PlanTier.PROFESSIONAL) == 3
        assert plan_max_accounts(PlanTier.BUSINESS) is None


# ---------------------------------------------------------------------------
# GoogleAdsAccount repository — delete method exists
# ---------------------------------------------------------------------------


class TestGoogleAdsAccountRepoContract:
    """Verify the delete method signature exists on the repository."""

    def test_delete_method_exists(self) -> None:
        from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
            SqlGoogleAdsAccountRepository,
        )

        assert hasattr(SqlGoogleAdsAccountRepository, "delete")

    def test_delete_method_is_async(self) -> None:
        import asyncio

        from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
            SqlGoogleAdsAccountRepository,
        )

        assert asyncio.iscoroutinefunction(SqlGoogleAdsAccountRepository.delete)


# ---------------------------------------------------------------------------
# Migration file — structural check
# ---------------------------------------------------------------------------


class TestMigration0053:
    def _load_migration(self):
        import importlib.util
        import pathlib

        path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "adcopilot"
            / "infrastructure"
            / "db"
            / "alembic"
            / "versions"
            / "0053_users_trial_started_at.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0053", path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_migration_has_correct_revision_chain(self) -> None:
        m = self._load_migration()
        assert m.revision == "0053"
        assert m.down_revision == "0052"

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        m = self._load_migration()
        assert callable(m.upgrade)
        assert callable(m.downgrade)
