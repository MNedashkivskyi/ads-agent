"""Unit tests for SnapshotAccountUseCase with fake/in-memory implementations."""

import uuid
from datetime import UTC, date, datetime

from adcopilot.application.ports.google_ads import CustomerInfo
from adcopilot.application.use_cases.snapshot_account import SnapshotAccountUseCase
from adcopilot.domain.entities import (
    AccountId,
    GoogleAdsAccount,
    OAuthCredentials,
    UserId,
)
from adcopilot.domain.exceptions import GoogleAdsAuthError
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    AudiencePerformanceSnapshot,
    CampaignSnapshot,
    ConversionActionSnapshot,
    DayOfWeekPerformanceSnapshot,
    DevicePerformanceSnapshot,
    GeoPerformanceSnapshot,
    HourPerformanceSnapshot,
    KeywordSnapshot,
    NegativeKeywordSnapshot,
    SearchTermSnapshot,
    SnapshotId,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ACCOUNT_ID = AccountId(str(uuid.uuid4()))
_USER_ID = UserId(str(uuid.uuid4()))
_SNAPSHOT_DATE = date(2026, 1, 15)


def _make_account(needs_reauth: bool = False) -> GoogleAdsAccount:
    return GoogleAdsAccount(
        id=_ACCOUNT_ID,
        user_id=_USER_ID,
        customer_id="123-456-7890",
        descriptive_name="Test Account",
        currency="USD",
        timezone="UTC",
        is_manager=False,
        write_enabled=False,
        connected_at=datetime(2026, 1, 1, tzinfo=UTC),
        needs_reauth=needs_reauth,
    )


def _make_creds() -> OAuthCredentials:
    return OAuthCredentials(
        account_id=_ACCOUNT_ID,
        refresh_token="test-refresh-token",
        access_token=None,
        expires_at=None,
    )


def _make_campaign(n: int = 1) -> CampaignSnapshot:
    return CampaignSnapshot(
        id=SnapshotId(str(uuid.uuid4())),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAPSHOT_DATE,
        campaign_id=n,
        name=f"Campaign {n}",
        status="ENABLED",
        channel_type="SEARCH",
        budget_micros=5_000_000,
        bidding_strategy="TARGET_CPA",
        impressions=1000,
        clicks=50,
        cost_micros=2_000_000,
        conversions=5.0,
        conv_value=500.0,
    )


# ---------------------------------------------------------------------------
# Fake implementations
# ---------------------------------------------------------------------------


class FakeGoogleAdsClient:
    def __init__(
        self,
        campaigns: list[CampaignSnapshot] | None = None,
        raise_auth_error: bool = False,
    ) -> None:
        self._campaigns = campaigns or [_make_campaign()]
        self._raise_auth_error = raise_auth_error

    async def list_accessible_customers(self, refresh_token: str) -> list[str]:
        return []

    async def get_customer_info(self, refresh_token: str, customer_id: str) -> CustomerInfo:
        return CustomerInfo(descriptive_name="", currency="USD", timezone="UTC", is_manager=False)

    async def query_campaigns(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[CampaignSnapshot]:
        if self._raise_auth_error:
            raise GoogleAdsAuthError("invalid credentials")
        return self._campaigns

    async def query_ad_groups(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[AdGroupSnapshot]:
        if self._raise_auth_error:
            raise GoogleAdsAuthError("invalid credentials")
        return []

    async def query_keywords(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[KeywordSnapshot]:
        if self._raise_auth_error:
            raise GoogleAdsAuthError("invalid credentials")
        return []

    async def query_search_terms(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[SearchTermSnapshot]:
        if self._raise_auth_error:
            raise GoogleAdsAuthError("invalid credentials")
        return []

    async def query_ads(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[AdSnapshot]:
        if self._raise_auth_error:
            raise GoogleAdsAuthError("invalid credentials")
        return []

    async def query_negative_keywords(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[NegativeKeywordSnapshot]:
        if self._raise_auth_error:
            raise GoogleAdsAuthError("invalid credentials")
        return []

    async def query_device_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[DevicePerformanceSnapshot]:
        if self._raise_auth_error:
            raise GoogleAdsAuthError("invalid credentials")
        return []

    async def query_geo_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[GeoPerformanceSnapshot]:
        if self._raise_auth_error:
            raise GoogleAdsAuthError("invalid credentials")
        return []

    async def query_hour_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[HourPerformanceSnapshot]:
        if self._raise_auth_error:
            raise GoogleAdsAuthError("invalid credentials")
        return []

    async def query_day_of_week_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[DayOfWeekPerformanceSnapshot]:
        if self._raise_auth_error:
            raise GoogleAdsAuthError("invalid credentials")
        return []

    async def query_audience_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[AudiencePerformanceSnapshot]:
        if self._raise_auth_error:
            raise GoogleAdsAuthError("invalid credentials")
        return []

    async def query_conversion_actions(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[ConversionActionSnapshot]:
        if self._raise_auth_error:
            raise GoogleAdsAuthError("invalid credentials")
        return []


class FakeSnapshotRepository:
    def __init__(self) -> None:
        self.campaigns: list[CampaignSnapshot] = []
        self.ad_groups: list[AdGroupSnapshot] = []
        self.keywords: list[KeywordSnapshot] = []
        self.search_terms: list[SearchTermSnapshot] = []
        self.ads: list[AdSnapshot] = []
        self.negative_keywords: list[NegativeKeywordSnapshot] = []

    async def upsert_campaigns(
        self, account_id: AccountId, snapshots: list[CampaignSnapshot]
    ) -> None:
        # Simple upsert: replace any matching (account_id, snapshot_date, campaign_id)
        self.campaigns = [
            s for s in self.campaigns
            if (s.account_id, s.snapshot_date, s.campaign_id) not in
            {(n.account_id, n.snapshot_date, n.campaign_id) for n in snapshots}
        ]
        self.campaigns.extend(snapshots)

    async def upsert_ad_groups(
        self, account_id: AccountId, snapshots: list[AdGroupSnapshot]
    ) -> None:
        self.ad_groups = [
            s for s in self.ad_groups
            if (s.account_id, s.snapshot_date, s.ad_group_id) not in
            {(n.account_id, n.snapshot_date, n.ad_group_id) for n in snapshots}
        ]
        self.ad_groups.extend(snapshots)

    async def upsert_keywords(
        self, account_id: AccountId, snapshots: list[KeywordSnapshot]
    ) -> None:
        self.keywords.extend(snapshots)

    async def upsert_search_terms(
        self, account_id: AccountId, snapshots: list[SearchTermSnapshot]
    ) -> None:
        self.search_terms.extend(snapshots)

    async def upsert_ads(
        self, account_id: AccountId, snapshots: list[AdSnapshot]
    ) -> None:
        self.ads.extend(snapshots)

    async def upsert_negative_keywords(
        self, account_id: AccountId, snapshots: list[NegativeKeywordSnapshot]
    ) -> None:
        self.negative_keywords.extend(snapshots)

    async def upsert_device_performance(
        self, account_id: AccountId, snapshots: list[DevicePerformanceSnapshot]
    ) -> None:
        pass

    async def upsert_geo_performance(
        self, account_id: AccountId, snapshots: list[GeoPerformanceSnapshot]
    ) -> None:
        pass

    async def upsert_hour_performance(
        self, account_id: AccountId, snapshots: list[HourPerformanceSnapshot]
    ) -> None:
        pass

    async def upsert_day_of_week_performance(
        self, account_id: AccountId, snapshots: list[DayOfWeekPerformanceSnapshot]
    ) -> None:
        pass

    async def upsert_audience_performance(
        self, account_id: AccountId, snapshots: list[AudiencePerformanceSnapshot]
    ) -> None:
        pass

    async def upsert_conversion_actions(
        self, account_id: AccountId, snapshots: list[ConversionActionSnapshot]
    ) -> None:
        pass

    async def get_latest_snapshot_date(self, account_id: AccountId) -> date | None:
        dates = [s.snapshot_date for s in self.campaigns if s.account_id == account_id]
        return max(dates) if dates else None


_SENTINEL = object()


class FakeAccountRepository:
    def __init__(self, account: GoogleAdsAccount | None = _SENTINEL) -> None:  # type: ignore[assignment]
        self._account: GoogleAdsAccount | None = _make_account() if account is _SENTINEL else account
        self.saved: GoogleAdsAccount | None = None

    async def get(self, account_id: AccountId) -> GoogleAdsAccount | None:
        if self._account and self._account.id == account_id:
            return self._account
        return None

    async def list_for_user(self, user_id: UserId) -> list[GoogleAdsAccount]:
        return [self._account] if self._account else []

    async def list_active(self) -> list[GoogleAdsAccount]:
        if self._account and not self._account.needs_reauth:
            return [self._account]
        return []

    async def save(self, account: GoogleAdsAccount) -> GoogleAdsAccount:
        self.saved = account
        self._account = account
        return account


class FakeCredentialsRepository:
    def __init__(self, creds: OAuthCredentials | None = _SENTINEL) -> None:  # type: ignore[assignment]
        self._creds: OAuthCredentials | None = _make_creds() if creds is _SENTINEL else creds

    async def get(self, account_id: AccountId) -> OAuthCredentials | None:
        if self._creds and self._creds.account_id == account_id:
            return self._creds
        return None

    async def save(self, credentials: OAuthCredentials) -> OAuthCredentials:
        self._creds = credentials
        return credentials


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_execute_returns_correct_counts() -> None:
    snap_repo = FakeSnapshotRepository()
    use_case = SnapshotAccountUseCase(
        ads_client=FakeGoogleAdsClient(campaigns=[_make_campaign(1), _make_campaign(2)]),
        snapshot_repo=snap_repo,
        credentials_repo=FakeCredentialsRepository(),
        account_repo=FakeAccountRepository(),
    )

    result = await use_case.execute(_ACCOUNT_ID, _SNAPSHOT_DATE)

    assert result.success is True
    assert result.campaigns == 2
    assert result.ad_groups == 0
    assert result.keywords == 0
    assert result.duration_seconds >= 0.0
    assert len(snap_repo.campaigns) == 2


async def test_idempotency_running_twice_same_date() -> None:
    """Running execute twice with the same date must produce the same final state."""
    snap_repo = FakeSnapshotRepository()
    campaign = _make_campaign(1)
    use_case = SnapshotAccountUseCase(
        ads_client=FakeGoogleAdsClient(campaigns=[campaign]),
        snapshot_repo=snap_repo,
        credentials_repo=FakeCredentialsRepository(),
        account_repo=FakeAccountRepository(),
    )

    await use_case.execute(_ACCOUNT_ID, _SNAPSHOT_DATE)
    await use_case.execute(_ACCOUNT_ID, _SNAPSHOT_DATE)

    # After two runs, there should still be only 1 campaign row for this date/id
    matching = [
        c for c in snap_repo.campaigns
        if c.campaign_id == 1 and c.snapshot_date == _SNAPSHOT_DATE
    ]
    assert len(matching) == 1


async def test_auth_error_sets_needs_reauth_and_does_not_raise() -> None:
    """GoogleAdsAuthError must set needs_reauth=True and return a failed SnapshotResult."""
    acc_repo = FakeAccountRepository(_make_account(needs_reauth=False))
    use_case = SnapshotAccountUseCase(
        ads_client=FakeGoogleAdsClient(raise_auth_error=True),
        snapshot_repo=FakeSnapshotRepository(),
        credentials_repo=FakeCredentialsRepository(),
        account_repo=acc_repo,
    )

    result = await use_case.execute(_ACCOUNT_ID, _SNAPSHOT_DATE)

    assert result.success is False
    assert result.campaigns == 0
    assert "GoogleAdsAuthError" in (result.error_message or "")

    # Account must have been saved with needs_reauth=True
    assert acc_repo.saved is not None
    assert acc_repo.saved.needs_reauth is True


async def test_missing_credentials_returns_failed_result() -> None:
    creds_repo = FakeCredentialsRepository(creds=None)  # type: ignore[arg-type]
    use_case = SnapshotAccountUseCase(
        ads_client=FakeGoogleAdsClient(),
        snapshot_repo=FakeSnapshotRepository(),
        credentials_repo=creds_repo,
        account_repo=FakeAccountRepository(),
    )

    result = await use_case.execute(_ACCOUNT_ID, _SNAPSHOT_DATE)

    assert result.success is False
    assert result.campaigns == 0


async def test_missing_account_returns_failed_result() -> None:
    acc_repo = FakeAccountRepository(account=None)
    use_case = SnapshotAccountUseCase(
        ads_client=FakeGoogleAdsClient(),
        snapshot_repo=FakeSnapshotRepository(),
        credentials_repo=FakeCredentialsRepository(),
        account_repo=acc_repo,
    )

    result = await use_case.execute(_ACCOUNT_ID, _SNAPSHOT_DATE)

    assert result.success is False
