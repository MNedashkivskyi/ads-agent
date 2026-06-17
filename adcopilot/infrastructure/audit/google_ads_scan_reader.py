"""Live read-only Google Ads reader for the audit scan (Audit Funnel Phase 2 / T2.1).

Implements ``AuditScanReader`` with windowed (``LAST_N_DAYS``) GAQL pulls that
mirror the proven per-day snapshot queries (``infrastructure/google_ads/queries``)
but aggregate over the audit window. Read-only by policy: only ``search_stream``
reads, never mutations.

NOTE: exercised against the live Google Ads API and verified in staging — it is
not unit-tested (no API credentials in CI), exactly like the OAuth flow. The
orchestration that uses it (``RunAuditScanUseCase``) is fully unit-tested via a
fake reader.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import structlog

from adcopilot.application.audit.scan_reader import AuditRawData
from adcopilot.config import Settings
from adcopilot.domain.entities import AccountId
from adcopilot.domain.exceptions import GoogleAdsAuthError, GoogleAdsUnavailable
from adcopilot.domain.snapshot import (
    CampaignSnapshot,
    ConversionActionSnapshot,
    KeywordSnapshot,
    SearchTermSnapshot,
)
from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter
from adcopilot.infrastructure.google_ads.queries import _build_client, _make_id, _wrap_exc

logger = structlog.get_logger(__name__)


def _ag_id(resource_name: str) -> int:
    return int(resource_name.split("/")[-1]) if resource_name else 0


class GoogleAdsAuditScanReader:
    """AuditScanReader backed by the live Google Ads API (read-only)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = GoogleAdsClientAdapter(settings)

    async def accessible_customers(self, refresh_token: str) -> list[str]:
        return await self._client.list_accessible_customers(refresh_token)

    async def pull(self, refresh_token: str, customer_id: str, days: int) -> AuditRawData:
        campaigns, search_terms, keywords, conversion_actions = await asyncio.gather(
            self._query(
                refresh_token, customer_id, _campaigns_query(days), _map_campaign, customer_id
            ),
            self._query(
                refresh_token, customer_id, _search_terms_query(days), _map_search_term, customer_id
            ),
            self._query(
                refresh_token, customer_id, _keywords_query(days), _map_keyword, customer_id
            ),
            self._query(
                refresh_token,
                customer_id,
                _conversion_actions_query(days),
                _map_conversion_action,
                customer_id,
            ),
        )
        return AuditRawData(
            campaigns=campaigns,
            search_terms=search_terms,
            keywords=keywords,
            conversion_actions=conversion_actions,
        )

    async def _query(
        self,
        refresh_token: str,
        customer_id: str,
        query: str,
        mapper: Any,
        raw_customer_id: str,
    ) -> list[Any]:
        def _blocking() -> list[Any]:
            client = _build_client(refresh_token, self._settings)
            service = client.get_service("GoogleAdsService")
            account_id = AccountId(raw_customer_id)
            out: list[Any] = []
            stream = service.search_stream(customer_id=customer_id.replace("-", ""), query=query)
            for batch in stream:
                for row in batch.results:
                    out.append(mapper(row, account_id))
            return out

        try:
            return await asyncio.wait_for(asyncio.to_thread(_blocking), timeout=90)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:
            raise _wrap_exc(exc) from exc


# --- GAQL (windowed, aggregated over the audit window) ----------------------


def _campaigns_query(days: int) -> str:
    return f"""
        SELECT campaign.id, campaign.name, campaign.status,
               campaign.advertising_channel_type, campaign_budget.amount_micros,
               campaign.bidding_strategy_type, metrics.impressions, metrics.clicks,
               metrics.cost_micros, metrics.conversions, metrics.conversions_value,
               metrics.search_budget_lost_impression_share
        FROM campaign WHERE segments.date DURING LAST_{days}_DAYS
    """


def _search_terms_query(days: int) -> str:
    return f"""
        SELECT search_term_view.search_term, search_term_view.ad_group,
               metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
        FROM search_term_view WHERE segments.date DURING LAST_{days}_DAYS
    """


def _keywords_query(days: int) -> str:
    return f"""
        SELECT ad_group_criterion.criterion_id, ad_group_criterion.ad_group,
               ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type,
               ad_group_criterion.status, ad_group_criterion.quality_info.quality_score,
               metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions,
               metrics.ctr, metrics.average_cpc
        FROM keyword_view WHERE segments.date DURING LAST_{days}_DAYS
    """


def _conversion_actions_query(days: int) -> str:
    return f"""
        SELECT conversion_action.id, conversion_action.name, conversion_action.category,
               conversion_action.counting_type, conversion_action.status,
               conversion_action.include_in_conversions_metric, metrics.all_conversions
        FROM conversion_action WHERE segments.date DURING LAST_{days}_DAYS
    """


# --- row mappers (mirror infrastructure/google_ads/queries.py) --------------


def _map_campaign(row: Any, account_id: AccountId) -> CampaignSnapshot:
    c, b, m = row.campaign, row.campaign_budget, row.metrics
    lost = m.search_budget_lost_impression_share
    return CampaignSnapshot(
        id=_make_id(),
        account_id=account_id,
        snapshot_date=date.today(),
        campaign_id=c.id,
        name=c.name,
        status=c.status.name,
        channel_type=c.advertising_channel_type.name,
        budget_micros=b.amount_micros,
        bidding_strategy=c.bidding_strategy_type.name,
        impressions=m.impressions,
        clicks=m.clicks,
        cost_micros=m.cost_micros,
        conversions=m.conversions,
        conv_value=m.conversions_value,
        search_budget_lost_impression_share=(None if lost in (0.0, float("inf")) else lost),
    )


def _map_search_term(row: Any, account_id: AccountId) -> SearchTermSnapshot:
    stv, m = row.search_term_view, row.metrics
    return SearchTermSnapshot(
        id=_make_id(),
        account_id=account_id,
        snapshot_date=date.today(),
        search_term=stv.search_term,
        ad_group_id=_ag_id(stv.ad_group),
        impressions=m.impressions,
        clicks=m.clicks,
        cost_micros=m.cost_micros,
        conversions=m.conversions,
        matched_keyword_id=None,
    )


def _map_keyword(row: Any, account_id: AccountId) -> KeywordSnapshot:
    agc, m = row.ad_group_criterion, row.metrics
    qs = agc.quality_info.quality_score
    return KeywordSnapshot(
        id=_make_id(),
        account_id=account_id,
        snapshot_date=date.today(),
        criterion_id=agc.criterion_id,
        ad_group_id=_ag_id(agc.ad_group),
        text=agc.keyword.text,
        match_type=agc.keyword.match_type.name,
        status=agc.status.name,
        quality_score=int(qs) if qs else None,
        impressions=m.impressions,
        clicks=m.clicks,
        cost_micros=m.cost_micros,
        conversions=m.conversions,
        ctr=m.ctr,
        avg_cpc_micros=m.average_cpc,
    )


def _map_conversion_action(row: Any, account_id: AccountId) -> ConversionActionSnapshot:
    ca = row.conversion_action
    return ConversionActionSnapshot(
        id=_make_id(),
        account_id=account_id,
        snapshot_date=date.today(),
        conversion_action_id=ca.id,
        name=ca.name,
        category=ca.category.name,
        counting_type=ca.counting_type.name,
        status=ca.status.name,
        include_in_conversions_metric=ca.include_in_conversions_metric,
        all_conversions=float(row.metrics.all_conversions),
    )
