import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Re-export for convenience
__all__ = [
    "AdExperimentModel",
    "AdGroupSnapshotModel",
    "AdSnapshotModel",
    "AlertModel",
    "AudiencePerformanceSnapshotModel",
    "AuditLogModel",
    "Base",
    "BusinessEconomicsModel",
    "CampaignExtensionSnapshotModel",
    "CampaignSnapshotModel",
    "ConversionActionSnapshotModel",
    "ConversionOutcomeModel",
    "ConversionUploadModel",
    "DayOfWeekPerformanceSnapshotModel",
    "DevicePerformanceSnapshotModel",
    "DigestSentLogModel",
    "GA4CredentialsModel",
    "GA4PageSnapshotModel",
    "GeoPerformanceSnapshotModel",
    "GoogleAdsAccountModel",
    "HourPerformanceSnapshotModel",
    "KeywordQSHistoryModel",
    "KeywordSnapshotModel",
    "LaunchAdGroupModel",
    "LaunchAdModel",
    "LaunchBriefModel",
    "LaunchCalloutModel",
    "LaunchKeywordModel",
    "LaunchProposalModel",
    "LaunchSitelinkModel",
    "LaunchStructuredSnippetModel",
    "NegativeKeywordSnapshotModel",
    "NotificationModel",
    "OAuthCredentialsModel",
    "PromptVersionModel",
    "RecommendationModel",
    "RecommendationSnoozeModel",
    "SearchTermSnapshotModel",
    "SitelinkPerformanceSnapshotModel",
    "SnapshotRunModel",
    "UserModel",
    "ImplementationPartnerModel",
    "ImplementationRequestModel",
    "QSImprovementPlanModel",
    "PerformanceReportModel",
    "VerticalBenchmarkSnapshotModel",
    # Campaign Intelligence Engine
    "DimensionPerformanceModel",
    "CieKeywordRunModel",
    "CieKeywordCandidateModel",
    "CieHookSetModel",
    "CieHookCandidateModel",
    "CieShippedKeywordModel",
    "CieShippedAssetModel",
    "CieAdsPerformanceFactModel",
    "CieSearchTermProposalModel",
    # Audit funnel (Phase 0)
    "AuditSessionModel",
    "WasteReportModel",
    "WasteFindingModel",
    "RecoveryLedgerModel",
]


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(nullable=True)
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="starter")
    notifications_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notification_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=9)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="pl")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subscription_status: Mapped[str] = mapped_column(String(50), nullable=False, default="trialing")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class GoogleAdsAccountModel(Base):
    __tablename__ = "google_ads_accounts"
    __table_args__ = (
        # A Google Ads customer_id may only ever be linked to ONE Adswise
        # user — prevents re-using the same Ads account across accounts to
        # get repeated free trials.
        Index("uq_google_ads_accounts_customer_id", "customer_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    descriptive_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    is_manager: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    write_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    needs_reauth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Vertical classification (populated after first snapshot; re-run monthly)
    vertical: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    sub_vertical: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    vertical_classified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OAuthCredentialsModel(Base):
    __tablename__ = "oauth_credentials"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    refresh_token_encrypted: Mapped[str] = mapped_column(String(2048), nullable=False)
    access_token_encrypted: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CampaignSnapshotModel(Base):
    __tablename__ = "campaign_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    channel_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    budget_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bidding_strategy: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    conv_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    search_impression_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    search_budget_lost_impression_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    search_rank_lost_impression_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_cpa_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    all_conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AdGroupSnapshotModel(Base):
    __tablename__ = "ad_group_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    ad_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KeywordSnapshotModel(Base):
    __tablename__ = "keyword_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    criterion_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ad_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    match_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_ctr: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ad_relevance: Mapped[str | None] = mapped_column(String(50), nullable=True)
    landing_page_experience: Mapped[str | None] = mapped_column(String(50), nullable=True)
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ctr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_cpc_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KeywordQSHistoryModel(Base):
    __tablename__ = "keyword_qs_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    criterion_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recorded_date: Mapped[date] = mapped_column(Date, nullable=False)
    keyword_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    match_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_ctr: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ad_relevance: Mapped[str | None] = mapped_column(String(50), nullable=True)
    landing_page_experience: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SearchTermSnapshotModel(Base):
    __tablename__ = "search_term_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    search_term: Mapped[str] = mapped_column(Text, nullable=False)
    ad_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    matched_keyword_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AdSnapshotModel(Base):
    __tablename__ = "ad_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    ad_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ad_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    headlines_json: Mapped[str] = mapped_column(JSONB, nullable=False, default="[]")
    descriptions_json: Mapped[str] = mapped_column(JSONB, nullable=False, default="[]")
    final_urls_json: Mapped[str] = mapped_column(JSONB, nullable=False, default="[]")
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ad_strength: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DevicePerformanceSnapshotModel(Base):
    __tablename__ = "device_performance_snapshots"
    __table_args__ = (
        Index(
            "uq_device_performance_snapshots",
            "account_id",
            "snapshot_date",
            "campaign_id",
            "device",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    device: Mapped[str] = mapped_column(String(50), nullable=False)
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class GeoPerformanceSnapshotModel(Base):
    __tablename__ = "geo_performance_snapshots"
    __table_args__ = (
        Index(
            "uq_geo_performance_snapshots",
            "account_id",
            "snapshot_date",
            "campaign_id",
            "location_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    location_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class HourPerformanceSnapshotModel(Base):
    __tablename__ = "hour_performance_snapshots"
    __table_args__ = (
        Index(
            "uq_hour_performance_snapshots",
            "account_id",
            "snapshot_date",
            "campaign_id",
            "hour_of_day",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hour_of_day: Mapped[int] = mapped_column(Integer, nullable=False)
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DayOfWeekPerformanceSnapshotModel(Base):
    __tablename__ = "day_of_week_performance_snapshots"
    __table_args__ = (
        Index(
            "uq_day_of_week_performance_snapshots",
            "account_id",
            "snapshot_date",
            "campaign_id",
            "day_of_week",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    day_of_week: Mapped[str] = mapped_column(String(20), nullable=False)
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AudiencePerformanceSnapshotModel(Base):
    __tablename__ = "audience_performance_snapshots"
    __table_args__ = (
        Index(
            "uq_audience_performance_snapshots",
            "account_id",
            "snapshot_date",
            "campaign_id",
            "ad_group_id",
            "criterion_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ad_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    criterion_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class NegativeKeywordSnapshotModel(Base):
    __tablename__ = "negative_keyword_snapshots"
    __table_args__ = (
        Index(
            "uq_negative_keyword_snapshots",
            "account_id",
            "snapshot_date",
            "campaign_id",
            "ad_group_id",
            "criterion_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    criterion_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ad_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    match_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ConversionActionSnapshotModel(Base):
    __tablename__ = "conversion_action_snapshots"
    __table_args__ = (
        Index(
            "uq_conversion_action_snapshots",
            "account_id",
            "snapshot_date",
            "conversion_action_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    conversion_action_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    counting_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    include_in_conversions_metric: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    all_conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CampaignExtensionSnapshotModel(Base):
    __tablename__ = "campaign_extension_snapshots"
    __table_args__ = (
        Index(
            "uq_campaign_extension_snapshots",
            "account_id",
            "snapshot_date",
            "campaign_id",
            "extension_type",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    extension_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SitelinkPerformanceSnapshotModel(Base):
    __tablename__ = "sitelink_performance_snapshots"
    __table_args__ = (
        Index(
            "uq_sitelink_performance_snapshots",
            "account_id",
            "snapshot_date",
            "campaign_id",
            "asset_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    asset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SnapshotRunModel(Base):
    __tablename__ = "snapshot_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    campaigns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ad_groups: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    keywords: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    search_terms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ads: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RecommendationSnoozeModel(Base):
    __tablename__ = "recommendation_snoozes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    target_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snoozed_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DigestSentLogModel(Base):
    __tablename__ = "digest_sent_log"
    __table_args__ = (Index("uq_digest_sent_log_user_date", "user_id", "sent_date", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    sent_date: Mapped[date] = mapped_column(Date, nullable=False)
    recommendation_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RecommendationModel(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        # Partial unique index: only one PENDING rec per (account, kind, target)
        Index(
            "uq_recommendations_pending",
            "account_id",
            "kind",
            "target_hash",
            unique=True,
            postgresql_where=sa.text("status = 'PENDING'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    target: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    target_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    estimated_monthly_savings_micros: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Campaign-launch domain models
# ---------------------------------------------------------------------------


class LaunchBriefModel(Base):
    """Persists a ``CampaignBrief`` aggregate."""

    __tablename__ = "launch_briefs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    business_description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    typical_customer_value: Mapped[sa.Numeric] = mapped_column(  # type: ignore[type-arg]
        Numeric(precision=14, scale=2), nullable=False
    )
    primary_action: Mapped[str] = mapped_column(String(255), nullable=False)
    monthly_budget_pln: Mapped[sa.Numeric] = mapped_column(  # type: ignore[type-arg]
        Numeric(precision=14, scale=2), nullable=False
    )
    # Stored as a JSON array of strings.
    exclusions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="pl")
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # 0 = not started, 1-6 = waiting for that question, 7 = summary/proposal shown,
    # 8 = awaiting revision text
    interview_step: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    # Google Ads resource name for the created campaign (e.g. "customers/123/campaigns/456").
    # Set after create_campaign succeeds; required for enable_campaign.
    campaign_resource_name: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    vertical: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LaunchProposalModel(Base):
    """Persists a ``CampaignProposal`` — the AI-generated campaign structure."""

    __tablename__ = "launch_proposals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("launch_briefs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_name: Mapped[str] = mapped_column(String(255), nullable=False)
    daily_budget_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    location_targeting: Mapped[str] = mapped_column(String(255), nullable=False)
    bidding_strategy: Mapped[str] = mapped_column(String(100), nullable=False)
    # Campaign-level negative keywords as a JSON array of strings.
    negative_keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    estimated_cpc_min_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    estimated_cpc_max_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Brand campaign fields (null for MICRO tier)
    brand_campaign_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    brand_keywords: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
    brand_daily_budget_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    brand_ad: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    seasonal_multiplier: Mapped[float] = mapped_column(nullable=False, default=1.0)
    seasonal_vertical: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    compliance_warnings: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LaunchAdGroupModel(Base):
    """Persists an ``AdGroupProposal`` belonging to a ``LaunchProposalModel``."""

    __tablename__ = "launch_ad_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("launch_proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Ordering within the proposal (0-based).
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Search-intent tier (HIGH_INTENT/MID_INTENT/DISCOVERY); NULL when untagged.
    intent_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # True when this group targets the advertiser's own brand terms.
    is_brand: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LaunchKeywordModel(Base):
    """Persists a ``KeywordProposal`` belonging to a ``LaunchAdGroupModel``."""

    __tablename__ = "launch_keywords"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ad_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("launch_ad_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), nullable=False)
    estimated_cpc_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # Real Keyword Planner search volume; NULL for template/LLM-only keywords.
    avg_monthly_searches: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Search-intent tier inherited from the ad group; NULL when untagged.
    intent_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LaunchAdModel(Base):
    """Persists an ``AdProposal`` belonging to a ``LaunchAdGroupModel``."""

    __tablename__ = "launch_ads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ad_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("launch_ad_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # RSA headlines and descriptions stored as JSON arrays.
    headlines: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    descriptions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    final_url: Mapped[str] = mapped_column(Text, nullable=False)
    path1: Mapped[str] = mapped_column(String(15), nullable=False, server_default="")
    path2: Mapped[str] = mapped_column(String(15), nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LaunchSitelinkModel(Base):
    """Persists a ``SitelinkProposal`` belonging to a ``LaunchProposalModel``."""

    __tablename__ = "launch_sitelinks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("launch_proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    link_text: Mapped[str] = mapped_column(String(25), nullable=False)
    description1: Mapped[str] = mapped_column(String(35), nullable=False)
    description2: Mapped[str] = mapped_column(String(35), nullable=False)
    final_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LaunchCalloutModel(Base):
    """Persists a ``CalloutProposal`` belonging to a ``LaunchProposalModel``."""

    __tablename__ = "launch_callouts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("launch_proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(String(25), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LaunchStructuredSnippetModel(Base):
    """Persists a ``StructuredSnippetProposal`` belonging to a ``LaunchProposalModel``."""

    __tablename__ = "launch_structured_snippets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("launch_proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    header: Mapped[str] = mapped_column(String(100), nullable=False)
    values: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Performance tracking models
# ---------------------------------------------------------------------------


class PerformanceBaselineModel(Base):
    __tablename__ = "recommendation_performance_baselines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    baseline_date: Mapped[date] = mapped_column(Date, nullable=False)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    conv_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cpa_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    ctr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PerformanceComparisonModel(Base):
    __tablename__ = "recommendation_performance_comparisons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    baseline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendation_performance_baselines.id", ondelete="CASCADE"),
        nullable=False,
    )
    comparison_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    current_cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_cpa_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    delta_cpa_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    delta_conversions_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    delta_ctr_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    compared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "recommendation_id", "comparison_window_days", name="uq_comparison_rec_window"
        ),
    )


# ---------------------------------------------------------------------------
# Anomaly alert model
# ---------------------------------------------------------------------------


class AlertModel(Base):
    """Persists a real-time anomaly Alert.

    Rate-limited to 3 per account per 24 hours. Separate from
    RecommendationModel because alerts require immediate attention and
    do not go through the approval workflow.
    """

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="CRITICAL")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class VerticalBenchmarkSnapshotModel(Base):
    """Anonymized performance aggregates per vertical × city_tier × week.

    Only stored when cohort has ≥5 accounts (privacy requirement).
    """

    __tablename__ = "vertical_benchmark_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vertical: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    city_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_week: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    account_count: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_cpa_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    median_cpa_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    p25_cpa_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    p75_cpa_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    avg_ctr: Mapped[float] = mapped_column(Float, nullable=False)
    avg_conversion_rate: Mapped[float] = mapped_column(Float, nullable=False)
    avg_monthly_spend_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_vbs_vertical_tier_week", "vertical", "city_tier", "snapshot_week"),)


class PromptVersionModel(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Deprecated prompts are retained for version history (the prompt-versioning
    # rule forbids deleting rows) but are no longer used by live code. Set for the
    # retired launch_structure / launch_ad_copy creation prompts in migration
    # 0075 (T2.4).
    deprecated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.false(), default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        sa.UniqueConstraint("prompt_key", "version", name="uq_prompt_versions_key_version"),
    )


class NotificationModel(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)


class QaConversationModel(Base):
    __tablename__ = "qa_conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    context_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_qa_conversations_user_created", "user_id", "created_at"),)


class AdExperimentModel(Base):
    __tablename__ = "ad_experiments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("google_ads_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_resource_name: Mapped[str] = mapped_column(Text, nullable=False)
    ad_group_resource_name: Mapped[str] = mapped_column(Text, nullable=False)
    control_ad_resource_name: Mapped[str] = mapped_column(Text, nullable=False)
    variant_ad_resource_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True)
    min_impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.95)
    winner: Mapped[str | None] = mapped_column(String(32), nullable=True)
    control_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    variant_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    concluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WeeklyInsightModel(Base):
    __tablename__ = "weekly_insights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    insight_text: Mapped[str] = mapped_column(Text, nullable=False)
    context_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ImplementationPartnerModel(Base):
    __tablename__ = "implementation_partners"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    voivodeship: Mapped[str] = mapped_column(String(100), nullable=False)
    platforms_supported: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    fixed_price_pln: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    avg_turnaround_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=48)
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    completed_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ImplementationRequestModel(Base):
    __tablename__ = "implementation_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="requested", index=True)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GA4CredentialsModel(Base):
    __tablename__ = "ga4_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    property_id: Mapped[str] = mapped_column(String(64), nullable=False)
    refresh_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class GA4PageSnapshotModel(Base):
    __tablename__ = "ga4_page_snapshots"
    __table_args__ = (
        Index(
            "uq_ga4_page_snapshots_account_date_path",
            "account_id",
            "snapshot_date",
            "page_path",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    page_path: Mapped[str] = mapped_column(Text, nullable=False)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bounce_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_session_duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    pages_per_session: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuctionInsightsSnapshotModel(Base):
    __tablename__ = "auction_insights_snapshots"
    __table_args__ = (
        Index(
            "uq_auction_insights_per_day",
            "account_id",
            "campaign_id",
            "competitor_domain",
            "snapshot_date",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    competitor_domain: Mapped[str] = mapped_column(Text, nullable=False)
    impression_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    overlap_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_above_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class QSImprovementPlanModel(Base):
    __tablename__ = "qs_improvement_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    keyword_criterion_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    target_ad_group_resource_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    current_avg_qs: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_qs: Mapped[float] = mapped_column(Float, nullable=False, default=7.0)
    bottleneck_component: Mapped[str] = mapped_column(String(64), nullable=False)
    prescribed_actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PROPOSED", index=True)
    baseline_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    current_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    evaluation_summary_pl: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    measurement_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PerformanceReportModel(Base):
    __tablename__ = "performance_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    report_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    summary_pl: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ConversionOutcomeModel(Base):
    """A captured real-world outcome (lead/sale) destined for Google Ads import."""

    __tablename__ = "conversion_outcomes"
    __table_args__ = (
        Index("ix_conversion_outcomes_account_status", "account_id", "status"),
        Index("ix_conversion_outcomes_upload", "account_id", "upload_status"),
        sa.UniqueConstraint(
            "account_id", "external_id", name="uq_conversion_outcomes_account_external"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    gclid: Mapped[str | None] = mapped_column(String(512), nullable=True)
    gbraid: Mapped[str | None] = mapped_column(String(512), nullable=True)
    wbraid: Mapped[str | None] = mapped_column(String(512), nullable=True)
    hashed_email: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hashed_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conversion_action_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="NEW")
    upload_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pending_adjustment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    adjusted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class BusinessEconomicsModel(Base):
    """Per-account unit economics for value-based bidding (Phase 5)."""

    __tablename__ = "business_economics"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    avg_order_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    profit_margin_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    customer_ltv: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    target_roas: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    default_lead_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN")
    # Business context (onboarding).
    primary_goal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    target_cpa: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    monthly_conversion_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brand_terms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    excluded_terms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CampaignExperimentModel(Base):
    """Native Google Ads campaign experiment (causal measurement)."""

    __tablename__ = "campaign_experiments"
    __table_args__ = (Index("ix_campaign_experiments_account_status", "account_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    base_campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    change_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    change_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    traffic_split: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PROPOSED", index=True)
    draft_resource_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    experiment_resource_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    control_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    treatment_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_recommendation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ConversionUploadModel(Base):
    """Audit row for one upload attempt (batch) to Google Ads."""

    __tablename__ = "conversion_uploads"
    __table_args__ = (Index("ix_conversion_uploads_account_created", "account_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validate_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SpendSafetyConfigModel(Base):
    """Per-account spend-safety caps + auto-pause toggle (spend-safety system)."""

    __tablename__ = "spend_safety_config"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    monthly_spend_cap_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    daily_spend_cap_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    per_campaign_daily_cap_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_budget_increase_pct: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False, default=50.0
    )
    warning_threshold_pct: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=80.0
    )
    auto_pause_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AutoApplySettingsModel(Base):
    """Per-account auto-apply opt-in (Phase 3 / T3.1).

    Default OFF. When enabled, low-risk recommendations (see
    ``adcopilot.domain.auto_apply``) are auto-approved and executed after
    detection, capped at ``max_changes_per_day`` and bounded by ``max_risk``,
    with SpendGuard still enforced at execution time.
    """

    __tablename__ = "auto_apply_settings"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.false(), default=False
    )
    max_risk: Mapped[str] = mapped_column(String(16), nullable=False, server_default="LOW")
    max_changes_per_day: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OrganizationModel(Base):
    """Organization — owns a set of users (team seats, Phase 3 / T3.4)."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    owner_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    is_personal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.true(), default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MembershipModel(Base):
    """A user's membership in an organization (Phase 3 / T3.4)."""

    __tablename__ = "memberships"
    __table_args__ = (
        sa.UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="MEMBER")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OrganizationInvitationModel(Base):
    """A pending invitation to join an organization (Phase 3 / T3.4)."""

    __tablename__ = "organization_invitations"
    __table_args__ = (
        sa.UniqueConstraint("organization_id", "email", name="uq_org_invites_org_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="MEMBER")
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ApiKeyModel(Base):
    """Customer API keys (Phase 3 / T3.5). Stores only the SHA-256 hash."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    display_prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssetGroupSnapshotModel(Base):
    __tablename__ = "asset_group_snapshots"
    __table_args__ = (
        sa.UniqueConstraint(
            "account_id", "snapshot_date", "asset_group_id", name="uq_asset_group_snapshots"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    asset_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    ad_strength: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    primary_status: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    conv_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ListingGroupSnapshotModel(Base):
    __tablename__ = "listing_group_snapshots"
    __table_args__ = (
        sa.UniqueConstraint(
            "account_id", "snapshot_date", "listing_group_id", name="uq_listing_group_snapshots"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    asset_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    listing_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dimension_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    case_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_catch_all: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ===========================================================================
# Campaign Intelligence Engine (CIE)
#
# Unified keyword + hook generation with a shared learning spine. Tables are
# prefixed ``cie_`` to keep the new subsystem cleanly separated from the legacy
# launch/snapshot schema. See ``adcopilot.domain.campaign_intelligence``.
# ===========================================================================


class DimensionPerformanceModel(Base):
    """Learned weights per (vertical, dimension, value, language) — the moat.

    One row says how a dimension value (a keyword intent-type or a creative
    angle) performs across every campaign in a vertical. ``dimension`` namespaces
    the two tracks ("keyword_intent" vs "angle") through one table and one
    learner.
    """

    __tablename__ = "cie_dimension_performance"
    __table_args__ = (
        sa.UniqueConstraint(
            "vertical",
            "dimension",
            "value",
            "language",
            name="uq_cie_dimension_performance_key",
        ),
        Index("ix_cie_dimperf_vertical_dimension", "vertical", "dimension"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical: Mapped[str] = mapped_column(String(64), nullable=False)
    dimension: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="pl")
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    conversions: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    weighted_ctr: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    weighted_conv: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    smoothed_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CieKeywordRunModel(Base):
    """One keyword-generation run for a campaign — the pollable job."""

    __tablename__ = "cie_keyword_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    vertical: Mapped[str] = mapped_column(String(64), nullable=False, server_default="generic")
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="pl")
    service: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    problems: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    seeds: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="generating", index=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CieKeywordCandidateModel(Base):
    """A generated keyword candidate, tagged by intent-type (the dimension)."""

    __tablename__ = "cie_keyword_candidates"
    __table_args__ = (
        sa.UniqueConstraint("run_id", "phrase", name="uq_cie_keyword_candidate_phrase"),
        Index("ix_cie_keyword_candidate_run_status", "run_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cie_keyword_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    phrase: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="llm")
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="generated")
    monthly_searches: Mapped[int | None] = mapped_column(Integer, nullable=True)
    competition: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cpc_low_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cpc_high_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_bucketed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CieHookSetModel(Base):
    """One hook-generation run for a campaign — owns the candidate hooks."""

    __tablename__ = "cie_hook_sets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    vertical: Mapped[str] = mapped_column(String(64), nullable=False, server_default="generic")
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="pl")
    service: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    problems: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="generating", index=True
    )
    rsa_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CieHookCandidateModel(Base):
    """A generated hook, tagged by angle (the dimension) + surface."""

    __tablename__ = "cie_hook_candidates"
    __table_args__ = (Index("ix_cie_hook_candidate_set_status", "set_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cie_hook_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    angle: Mapped[str] = mapped_column(String(32), nullable=False)
    surface: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    policy_risk: Mapped[str] = mapped_column(String(10), nullable=False, server_default="LOW")
    policy_reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    judge_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    heuristic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="generated")
    pinned_slot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CieShippedKeywordModel(Base):
    """A keyword shipped into a live ad group, tagged with its intent-type.

    The attribution map: nightly performance ingest joins per-keyword rows back
    to ``intent`` through this table. Without it, Layer 3 has nothing to learn
    from on the keyword track.
    """

    __tablename__ = "cie_shipped_keywords"
    __table_args__ = (
        sa.UniqueConstraint(
            "account_id",
            "customer_id",
            "keyword_text",
            "ad_group_id",
            name="uq_cie_shipped_keyword",
        ),
        Index("ix_cie_shipped_keyword_text", "keyword_text"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    external_campaign_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ad_group_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    criterion_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    keyword_text: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(16), nullable=False)
    vertical: Mapped[str] = mapped_column(String(64), nullable=False, server_default="generic")
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="pl")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CieShippedAssetModel(Base):
    """An ad asset shipped into a live RSA, tagged with its angle + surface.

    The attribution map for the creative track (mirror of shipped keywords).
    """

    __tablename__ = "cie_shipped_assets"
    __table_args__ = (
        sa.UniqueConstraint(
            "account_id",
            "customer_id",
            "asset_text",
            "surface",
            name="uq_cie_shipped_asset",
        ),
        Index("ix_cie_shipped_asset_text", "asset_text"),
        Index("ix_cie_shipped_asset_id", "asset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    asset_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    asset_text: Mapped[str] = mapped_column(Text, nullable=False)
    angle: Mapped[str] = mapped_column(String(32), nullable=False)
    surface: Mapped[str] = mapped_column(String(20), nullable=False)
    vertical: Mapped[str] = mapped_column(String(64), nullable=False, server_default="generic")
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="pl")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CieAdsPerformanceFactModel(Base):
    """Idempotent per-(entity, day) performance fact, pre-attributed to a dimension.

    The raw ground-truth ledger. ``recompute_dimension_weights`` aggregates these
    into ``cie_dimension_performance``. Unique on (account, entity_type, entity_id,
    day) so re-running an ingest is idempotent.
    """

    __tablename__ = "cie_ads_performance_facts"
    __table_args__ = (
        sa.UniqueConstraint(
            "account_id",
            "entity_type",
            "entity_id",
            "day",
            name="uq_cie_perf_fact",
        ),
        Index("ix_cie_perf_fact_dim", "vertical", "dimension", "value"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    dimension: Mapped[str | None] = mapped_column(String(64), nullable=True)
    value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vertical: Mapped[str] = mapped_column(String(64), nullable=False, server_default="generic")
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="pl")
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    conversions: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    performance_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CieSearchTermProposalModel(Base):
    """A harvested search term proposed as a new keyword or a negative.

    Surfaced to the user for one-click adoption. Unique on (account, term, kind)
    so harvesting is idempotent and doesn't duplicate prior proposals.
    """

    __tablename__ = "cie_search_term_proposals"
    __table_args__ = (
        sa.UniqueConstraint("account_id", "term", "kind", name="uq_cie_search_term_proposal"),
        Index("ix_cie_search_term_proposal_status", "account_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    term: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(16), nullable=True)
    vertical: Mapped[str] = mapped_column(String(64), nullable=False, server_default="generic")
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="pl")
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    conversions: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    ctr: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="proposed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Audit-funnel models (Audit Funnel Phase 0 / Task 0.1)
# ---------------------------------------------------------------------------


class AuditSessionModel(Base):
    """A (possibly anonymous) free-audit session keyed to a Google customer id."""

    __tablename__ = "audit_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    google_customer_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    oauth_scope: Mapped[str] = mapped_column(String(40), nullable=False, default="adwords-readonly")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="landing")
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WasteReportModel(Base):
    """The computed audit result — headline waste plus measurement gap."""

    __tablename__ = "waste_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("audit_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="PLN")
    total_spend_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    headline_waste_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    measurement_gap_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    methodology_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WasteFindingModel(Base):
    """One categorised finding within a report; ``evidence`` carries the proof."""

    __tablename__ = "waste_findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("waste_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    amount_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RecoveryLedgerModel(Base):
    """A realised (or projected) saving from applying a fix — powers the meter."""

    __tablename__ = "recovery_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    method: Mapped[str] = mapped_column(String(20), nullable=False, default="projected")
    baseline_metric: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    realized_saving_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
