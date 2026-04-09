from dataclasses import dataclass
from datetime import date
from typing import NewType

from adcopilot.domain.entities import AccountId

SnapshotId = NewType("SnapshotId", str)


@dataclass(frozen=True)
class CampaignSnapshot:
    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    campaign_id: int
    name: str
    status: str
    channel_type: str
    budget_micros: int
    bidding_strategy: str
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float
    conv_value: float


@dataclass(frozen=True)
class AdGroupSnapshot:
    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    ad_group_id: int
    campaign_id: int
    name: str
    status: str
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float


@dataclass(frozen=True)
class KeywordSnapshot:
    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    criterion_id: int
    ad_group_id: int
    text: str
    match_type: str
    status: str
    quality_score: int | None
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float
    ctr: float
    avg_cpc_micros: int


@dataclass(frozen=True)
class SearchTermSnapshot:
    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    search_term: str
    ad_group_id: int
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float
    matched_keyword_id: int | None


@dataclass(frozen=True)
class AdSnapshot:
    id: SnapshotId
    account_id: AccountId
    snapshot_date: date
    ad_id: int
    ad_group_id: int
    type: str
    status: str
    headlines_json: str
    descriptions_json: str
    final_urls_json: str
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float
