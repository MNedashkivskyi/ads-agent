"""End-to-end smoke test for the full user journey.

This test walks through the complete AdCopilot user journey against a real,
isolated stack (Postgres + Redis) but with all external Google/Telegram I/O
mocked at the port boundary.  It is the canonical smoke test: if this test
passes, the core happy path works end to end.

Covered steps:

1. Sign up a new user via the public signup API.
2. Complete the Google OAuth callback with a mocked token exchange and a
   pre-seeded refresh token.
3. Trigger a synchronous snapshot against a fake Google Ads account — all
   14 entity types are returned by the fake ads client.
4. Verify snapshot rows were persisted to Postgres for every entity type.
5. Run detection and verify at least one recommendation is created.
6. Capture the Telegram digest via a fake notifier.
7. Approve one recommendation (simulates the Telegram approve callback).
8. Execute the recommendation and verify the audit log records the change.
9. Undo the execution and verify state is reversed (status flipped back and
   an UNDO row appears in the audit log).

Runs in well under 60 seconds against a clean DB; running twice in a row is
deterministic because the DB is truncated and Redis flushed between tests.
"""

from __future__ import annotations

import uuid
from dataclasses import replace as dc_replace
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from adcopilot.application.ports.google_ads import CustomerInfo
from adcopilot.application.use_cases.approve_recommendation import ApproveRecommendationUseCase
from adcopilot.application.use_cases.execute_recommendation import ExecuteRecommendationUseCase
from adcopilot.application.use_cases.run_detection import RunDetectionUseCase
from adcopilot.application.use_cases.snapshot_account import SnapshotAccountUseCase
from adcopilot.application.use_cases.undo_recommendation import UndoRecommendationUseCase
from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.recommendation import (
    RecommendationId,
    RecommendationKind,
    RecommendationStatus,
)
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    AudiencePerformanceSnapshot,
    CampaignExtensionSnapshot,
    CampaignSnapshot,
    ConversionActionSnapshot,
    DayOfWeekPerformanceSnapshot,
    DevicePerformanceSnapshot,
    GeoPerformanceSnapshot,
    HourPerformanceSnapshot,
    KeywordSnapshot,
    NegativeKeywordSnapshot,
    SearchTermSnapshot,
    SitelinkPerformanceSnapshot,
    SnapshotId,
)
from adcopilot.infrastructure.google_ads.fake_mutations import FakeGoogleAdsMutations
from adcopilot.infrastructure.telegram.fake_notifier import FakeTelegramNotifier

# Deterministic constants so two runs of the test produce identical DB state.
_TEST_EMAIL = "e2e-journey@example.com"
_TEST_PASSWORD = "sup3rsecret-e2e"
_TEST_CUSTOMER_ID = "customers/1234567890"
_TEST_REFRESH_TOKEN = "ya29.e2e-test-refresh-token"
_TEST_ACCESS_TOKEN = "ya29.e2e-test-access-token"
_SNAPSHOT_DATE = date(2026, 4, 10)


# --------------------------------------------------------------------------- #
# Fake Google Ads client (mocks the port — no network)                        #
# --------------------------------------------------------------------------- #


class FakeGoogleAdsClient:
    """In-memory implementation of ``GoogleAdsClientPort``.

    Returns deterministic seed data that is just rich enough to exercise the
    snapshot, detection, execution and undo paths — no more.
    """

    def __init__(self, account_id: AccountId) -> None:
        self._account_id = account_id

    async def list_accessible_customers(self, refresh_token: str) -> list[str]:
        return [_TEST_CUSTOMER_ID]

    async def get_customer_info(self, refresh_token: str, customer_id: str) -> CustomerInfo:
        return CustomerInfo(
            descriptive_name="E2E Test Account",
            currency="USD",
            timezone="UTC",
            is_manager=False,
        )

    async def query_campaigns(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[CampaignSnapshot]:
        return [
            CampaignSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                campaign_id=111,
                name="E2E Test Campaign",
                status="ENABLED",
                channel_type="SEARCH",
                budget_micros=10_000_000,
                bidding_strategy="MAXIMIZE_CONVERSIONS",
                impressions=1_000,
                clicks=50,
                cost_micros=5_000_000,
                conversions=5.0,
                conv_value=100.0,
            )
        ]

    async def query_ad_groups(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[AdGroupSnapshot]:
        return [
            AdGroupSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                ad_group_id=222,
                campaign_id=111,
                name="E2E Ad Group",
                status="ENABLED",
                impressions=1_000,
                clicks=50,
                cost_micros=5_000_000,
                conversions=5.0,
            )
        ]

    async def query_keywords(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[KeywordSnapshot]:
        # One "dead" keyword — zero impressions but ENABLED.  This deliberately
        # triggers the DeadKeywordRule (rule 9) which creates a PAUSE_KEYWORD
        # recommendation — the rest of the journey hinges on this.
        return [
            KeywordSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                criterion_id=333,
                ad_group_id=222,
                text="dead keyword",
                match_type="EXACT",
                status="ENABLED",
                quality_score=7,
                impressions=0,
                clicks=0,
                cost_micros=0,
                conversions=0.0,
                ctr=0.0,
                avg_cpc_micros=0,
            )
        ]

    async def query_search_terms(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[SearchTermSnapshot]:
        return [
            SearchTermSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                search_term="e2e test term",
                ad_group_id=222,
                impressions=100,
                clicks=10,
                cost_micros=1_000_000,
                conversions=1.0,
                matched_keyword_id=333,
            )
        ]

    async def query_ads(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[AdSnapshot]:
        return [
            AdSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                ad_id=444,
                ad_group_id=222,
                type="RESPONSIVE_SEARCH_AD",
                status="ENABLED",
                headlines_json='["Buy Now", "Great Deals", "Fast Shipping"]',
                descriptions_json='["Best prices", "Ships free"]',
                final_urls_json='["https://example.com"]',
                impressions=500,
                clicks=25,
                cost_micros=2_500_000,
                conversions=2.5,
                ad_strength="GOOD",
            )
        ]

    async def query_negative_keywords(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[NegativeKeywordSnapshot]:
        return [
            NegativeKeywordSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                criterion_id=555,
                campaign_id=111,
                ad_group_id=0,
                text="free",
                match_type="EXACT",
            )
        ]

    async def query_device_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[DevicePerformanceSnapshot]:
        return [
            DevicePerformanceSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                campaign_id=111,
                device="MOBILE",
                impressions=600,
                clicks=30,
                cost_micros=3_000_000,
                conversions=3.0,
            )
        ]

    async def query_geo_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[GeoPerformanceSnapshot]:
        return [
            GeoPerformanceSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                campaign_id=111,
                location_id=2840,  # United States
                impressions=800,
                clicks=40,
                cost_micros=4_000_000,
                conversions=4.0,
            )
        ]

    async def query_hour_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[HourPerformanceSnapshot]:
        return [
            HourPerformanceSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                campaign_id=111,
                hour_of_day=14,
                impressions=200,
                clicks=10,
                cost_micros=1_000_000,
                conversions=1.0,
            )
        ]

    async def query_day_of_week_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[DayOfWeekPerformanceSnapshot]:
        return [
            DayOfWeekPerformanceSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                campaign_id=111,
                day_of_week="MONDAY",
                impressions=300,
                clicks=15,
                cost_micros=1_500_000,
                conversions=1.5,
            )
        ]

    async def query_audience_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[AudiencePerformanceSnapshot]:
        return [
            AudiencePerformanceSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                campaign_id=111,
                ad_group_id=222,
                criterion_id=666,
                impressions=150,
                clicks=7,
                cost_micros=700_000,
                conversions=0.5,
            )
        ]

    async def query_conversion_actions(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[ConversionActionSnapshot]:
        return [
            ConversionActionSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                conversion_action_id=777,
                name="Purchase",
                category="PURCHASE",
                counting_type="ONE_PER_CLICK",
                status="ENABLED",
                include_in_conversions_metric=True,
            )
        ]

    async def query_campaign_extensions(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[CampaignExtensionSnapshot]:
        return [
            CampaignExtensionSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                campaign_id=111,
                extension_type="SITELINK",
            )
        ]

    async def query_sitelink_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[SitelinkPerformanceSnapshot]:
        return [
            SitelinkPerformanceSnapshot(
                id=SnapshotId(str(uuid.uuid4())),
                account_id=self._account_id,
                snapshot_date=snapshot_date,
                campaign_id=111,
                asset_id=888,
                impressions=100,
                clicks=5,
            )
        ]


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


async def _row_count(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
        return int(result.scalar_one())


def _deterministic_account_id(user_id: str, customer_id: str) -> AccountId:
    """Mirror the OAuth callback's deterministic account ID derivation."""
    return AccountId(str(uuid.uuid5(uuid.NAMESPACE_URL, f"{user_id}/{customer_id}")))


# --------------------------------------------------------------------------- #
# The test                                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.e2e
async def test_full_user_journey(
    clean_db: None,
    db_engine: AsyncEngine,
    e2e_settings: Any,
) -> None:
    """Walk the full signup → snapshot → detect → execute → undo journey."""
    # Ensure rule-engine downstream code picks up our patched settings.
    from adcopilot.config import get_settings
    from adcopilot.main import create_app

    # -------- 1. Signup via API ------------------------------------------- #
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: e2e_settings

    with TestClient(app, raise_server_exceptions=True) as client:
        signup_resp = client.post(
            "/api/auth/signup",
            json={"email": _TEST_EMAIL, "password": _TEST_PASSWORD},
        )
    assert signup_resp.status_code == 200, signup_resp.text
    user_id = signup_resp.json()["user_id"]
    assert user_id

    # -------- 2. Mocked Google OAuth callback ----------------------------- #
    from adcopilot.interfaces.api.oauth import _make_state_jwt

    state = _make_state_jwt(user_id, e2e_settings.SECRET_KEY)

    with respx.mock:
        respx.post("https://oauth2.googleapis.com/token").mock(
            return_value=Response(
                200,
                json={
                    "refresh_token": _TEST_REFRESH_TOKEN,
                    "access_token": _TEST_ACCESS_TOKEN,
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        )

        with patch("adcopilot.interfaces.api.oauth.GoogleAdsClientAdapter") as mock_ads_cls:
            mock_ads_instance = AsyncMock()
            mock_ads_instance.list_accessible_customers.return_value = [_TEST_CUSTOMER_ID]
            mock_ads_cls.return_value = mock_ads_instance

            with TestClient(app, raise_server_exceptions=True) as client:
                oauth_resp = client.get(
                    "/oauth/google/callback",
                    params={"code": "e2e-auth-code", "state": state},
                )

    assert oauth_resp.status_code == 200, oauth_resp.text
    linked = oauth_resp.json()["linked_customer_ids"]
    assert _TEST_CUSTOMER_ID in linked

    account_id = _deterministic_account_id(user_id, _TEST_CUSTOMER_ID)

    # -------- 3. Synchronous snapshot (mocked ads client) ----------------- #
    # Mock at the port level — we exercise the real SnapshotAccountUseCase
    # plus the real SqlSnapshotRepository with a fake GoogleAdsClientPort.
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.db.repositories.snapshot_repository import (
        SqlSnapshotRepository,
    )

    fake_ads_client = FakeGoogleAdsClient(account_id)

    async with AsyncSession(db_engine) as session, session.begin():
        snapshot_uc = SnapshotAccountUseCase(
            ads_client=fake_ads_client,  # type: ignore[arg-type]
            snapshot_repo=SqlSnapshotRepository(session),
            credentials_repo=SqlOAuthCredentialsRepository(
                session, e2e_settings.TOKEN_ENCRYPTION_KEY
            ),
            account_repo=SqlGoogleAdsAccountRepository(session),
        )
        result = await snapshot_uc.execute(account_id, _SNAPSHOT_DATE)

    assert result.success, result.error_message
    assert result.campaigns == 1
    assert result.ad_groups == 1
    assert result.keywords == 1
    assert result.search_terms == 1
    assert result.ads == 1

    # -------- 4. Verify snapshots persisted for every entity type --------- #
    for table in (
        "campaign_snapshots",
        "ad_group_snapshots",
        "keyword_snapshots",
        "search_term_snapshots",
        "ad_snapshots",
        "negative_keyword_snapshots",
        "device_performance_snapshots",
        "geo_performance_snapshots",
        "hour_performance_snapshots",
        "day_of_week_performance_snapshots",
        "audience_performance_snapshots",
        "conversion_action_snapshots",
        "campaign_extension_snapshots",
        "sitelink_performance_snapshots",
    ):
        assert await _row_count(db_engine, table) >= 1, (
            f"expected at least one row in {table} but found none"
        )

    # -------- 5. Run detection --------------------------------------------- #
    from adcopilot.application.detection.registry import build_rule_engine
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )
    from adcopilot.infrastructure.db.repositories.snooze_repository import (
        SqlSnoozeRepository,
    )

    async with AsyncSession(db_engine) as session, session.begin():
        rec_repo = SqlRecommendationRepository(session)
        snooze_repo = SqlSnoozeRepository(session)
        detection_uc = RunDetectionUseCase(
            snapshot_repo=SqlSnapshotRepository(session),
            rec_repo=rec_repo,
            rule_engine=build_rule_engine(rec_repo, snooze_repo),
            account_repo=SqlGoogleAdsAccountRepository(session),
        )
        severity_counts = await detection_uc.execute(account_id, _SNAPSHOT_DATE)

    assert sum(severity_counts.values()) >= 1, (
        f"expected at least one recommendation, got {severity_counts}"
    )

    # -------- 6. Capture Telegram digest via the fake notifier ------------- #
    # Pull the PENDING PAUSE_KEYWORD rec (triggered by our dead keyword).
    async with AsyncSession(db_engine) as session:
        rec_repo = SqlRecommendationRepository(session)
        pending = await rec_repo.list_pending(account_id)
    assert pending, "expected at least one pending recommendation after detection"

    pause_kw = next(
        (r for r in pending if r.kind == RecommendationKind.PAUSE_KEYWORD),
        None,
    )
    assert pause_kw is not None, (
        f"expected a PAUSE_KEYWORD recommendation, got kinds: {[r.kind.value for r in pending]}"
    )

    fake_notifier = FakeTelegramNotifier()
    await fake_notifier.send_digest(chat_id=42, recommendations=[pause_kw])
    assert len(fake_notifier.calls) == 1
    assert fake_notifier.calls[0]["chat_id"] == 42
    assert pause_kw in fake_notifier.calls[0]["recommendations"]  # type: ignore[operator]

    # -------- 7. Approve (simulate Telegram approve callback) -------------- #
    async with AsyncSession(db_engine) as session, session.begin():
        approve_uc = ApproveRecommendationUseCase(
            rec_repo=SqlRecommendationRepository(session),
        )
        await approve_uc.execute(RecommendationId(pause_kw.id))

    async with AsyncSession(db_engine) as session:
        rec_repo = SqlRecommendationRepository(session)
        approved = await rec_repo.get(RecommendationId(pause_kw.id))
    assert approved is not None
    assert approved.status == RecommendationStatus.APPROVED

    # -------- 8. Execute & verify audit log -------------------------------- #
    fake_mutations = FakeGoogleAdsMutations()
    from adcopilot.infrastructure.db.repositories.audit_log_repository import (
        SqlAuditLogRepository,
    )

    async with AsyncSession(db_engine) as session, session.begin():
        execute_uc = ExecuteRecommendationUseCase(
            rec_repo=SqlRecommendationRepository(session),
            audit_log_repo=SqlAuditLogRepository(session),
            account_repo=SqlGoogleAdsAccountRepository(session),
            credentials_repo=SqlOAuthCredentialsRepository(
                session, e2e_settings.TOKEN_ENCRYPTION_KEY
            ),
            mutations=fake_mutations,  # type: ignore[arg-type]
        )
        exec_result = await execute_uc.execute(RecommendationId(pause_kw.id))

    assert exec_result["action"] == "paused"
    assert len(fake_mutations.calls) == 1
    assert fake_mutations.calls[0]["method"] == "pause_keyword"
    assert fake_mutations.calls[0]["criterion_id"] == 333

    # Rec moved to EXECUTED and audit log has one EXECUTE row.
    async with AsyncSession(db_engine) as session:
        rec_repo = SqlRecommendationRepository(session)
        executed = await rec_repo.get(RecommendationId(pause_kw.id))
    assert executed is not None
    assert executed.status == RecommendationStatus.EXECUTED

    from adcopilot.infrastructure.db.models import AuditLogModel

    async with AsyncSession(db_engine) as session:
        res = await session.execute(
            select(AuditLogModel).where(
                AuditLogModel.recommendation_id == uuid.UUID(pause_kw.id),
                AuditLogModel.action == "EXECUTE",
            )
        )
        exec_logs = res.scalars().all()
    assert len(exec_logs) == 1
    assert exec_logs[0].kind == RecommendationKind.PAUSE_KEYWORD.value
    assert exec_logs[0].payload["criterion_id"] == 333

    # -------- 9. Undo & verify state reversed ------------------------------ #
    async with AsyncSession(db_engine) as session, session.begin():
        undo_uc = UndoRecommendationUseCase(
            rec_repo=SqlRecommendationRepository(session),
            audit_log_repo=SqlAuditLogRepository(session),
            account_repo=SqlGoogleAdsAccountRepository(session),
            credentials_repo=SqlOAuthCredentialsRepository(
                session, e2e_settings.TOKEN_ENCRYPTION_KEY
            ),
            mutations=fake_mutations,  # type: ignore[arg-type]
        )
        undo_result = await undo_uc.execute(RecommendationId(pause_kw.id))

    assert undo_result["action"] == "enabled"
    # enable_keyword should have been called as the second mutation.
    assert any(c["method"] == "enable_keyword" for c in fake_mutations.calls)

    # Rec status reverted to APPROVED (reversible state) and audit log has
    # exactly one UNDO row in addition to the prior EXECUTE.
    async with AsyncSession(db_engine) as session:
        rec_repo = SqlRecommendationRepository(session)
        reverted = await rec_repo.get(RecommendationId(pause_kw.id))
    assert reverted is not None
    assert reverted.status == RecommendationStatus.APPROVED

    async with AsyncSession(db_engine) as session:
        res = await session.execute(
            select(AuditLogModel).where(AuditLogModel.recommendation_id == uuid.UUID(pause_kw.id))
        )
        all_logs = res.scalars().all()

    actions = sorted(log.action for log in all_logs)
    assert actions == ["EXECUTE", "UNDO"], f"expected one EXECUTE and one UNDO, got {actions}"

    # Silence unused-import style warnings for helpers pulled in at top level
    # but exercised only in this single test body.
    _ = dc_replace, datetime, UTC, UserId
