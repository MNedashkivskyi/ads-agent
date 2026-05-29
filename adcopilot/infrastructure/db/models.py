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
    "CampaignExtensionSnapshotModel",
    "CampaignSnapshotModel",
    "ConversionActionSnapshotModel",
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
