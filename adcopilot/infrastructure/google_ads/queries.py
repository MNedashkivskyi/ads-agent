"""GAQL query functions — each returns a list of domain snapshot DTOs."""

import json
import uuid
from datetime import date
from typing import Any

import structlog

from adcopilot.config import Settings
from adcopilot.domain.entities import AccountId
from adcopilot.domain.exceptions import GoogleAdsAuthError, GoogleAdsUnavailable
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    CampaignSnapshot,
    KeywordSnapshot,
    SearchTermSnapshot,
    SnapshotId,
)

logger = structlog.get_logger(__name__)


def _make_id() -> SnapshotId:
    return SnapshotId(str(uuid.uuid4()))


def _build_client(refresh_token: str, settings: Settings) -> Any:
    try:
        import google.ads.googleads.client as gads

        config = {
            "developer_token": settings.GOOGLE_ADS_DEVELOPER_TOKEN or "",
            "client_id": settings.GOOGLE_ADS_CLIENT_ID or "",
            "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET or "",
            "refresh_token": refresh_token,
            "use_proto_plus": True,
        }
        return gads.GoogleAdsClient.load_from_dict(config)
    except Exception as exc:
        raise GoogleAdsUnavailable(f"Failed to build Google Ads client: {exc}") from exc


def _wrap_exc(exc: Exception) -> Exception:
    error_str = str(exc).lower()
    if "unauthenticated" in error_str or "invalid credentials" in error_str:
        return GoogleAdsAuthError(str(exc))
    if "quota" in error_str or "resource exhausted" in error_str:
        from adcopilot.domain.exceptions import GoogleAdsRateLimited

        return GoogleAdsRateLimited(str(exc))
    return GoogleAdsUnavailable(str(exc))


async def query_campaigns(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[CampaignSnapshot]:
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    date_str = snapshot_date.isoformat()
    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            campaign_budget.amount_micros,
            campaign.bidding_strategy_type,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value
        FROM campaign
        WHERE segments.date = '{date_str}'
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[CampaignSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                c = row.campaign
                b = row.campaign_budget
                m = row.metrics
                results.append(
                    CampaignSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=snapshot_date,
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
                    )
                )
        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def query_ad_groups(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[AdGroupSnapshot]:
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    date_str = snapshot_date.isoformat()
    query = f"""
        SELECT
            ad_group.id,
            ad_group.name,
            ad_group.status,
            ad_group.campaign,
            campaign.id,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM ad_group
        WHERE segments.date = '{date_str}'
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[AdGroupSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                ag = row.ad_group
                m = row.metrics
                results.append(
                    AdGroupSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=snapshot_date,
                        ad_group_id=ag.id,
                        campaign_id=row.campaign.id,
                        name=ag.name,
                        status=ag.status.name,
                        impressions=m.impressions,
                        clicks=m.clicks,
                        cost_micros=m.cost_micros,
                        conversions=m.conversions,
                    )
                )
        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def query_keywords(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[KeywordSnapshot]:
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    date_str = snapshot_date.isoformat()
    query = f"""
        SELECT
            ad_group_criterion.criterion_id,
            ad_group_criterion.ad_group,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status,
            ad_group_criterion.quality_info.quality_score,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.ctr,
            metrics.average_cpc
        FROM keyword_view
        WHERE segments.date = '{date_str}'
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[KeywordSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                agc = row.ad_group_criterion
                m = row.metrics
                qs = agc.quality_info.quality_score
                # Extract ad_group_id from resource name customers/{cid}/adGroups/{id}
                ag_resource = agc.ad_group
                ag_id = int(ag_resource.split("/")[-1]) if ag_resource else 0
                results.append(
                    KeywordSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=snapshot_date,
                        criterion_id=agc.criterion_id,
                        ad_group_id=ag_id,
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
                )
        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def query_search_terms(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[SearchTermSnapshot]:
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    date_str = snapshot_date.isoformat()
    query = f"""
        SELECT
            search_term_view.search_term,
            search_term_view.ad_group,
            search_term_view.status,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM search_term_view
        WHERE segments.date = '{date_str}'
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[SearchTermSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                stv = row.search_term_view
                m = row.metrics
                ag_resource = stv.ad_group
                ag_id = int(ag_resource.split("/")[-1]) if ag_resource else 0
                results.append(
                    SearchTermSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=snapshot_date,
                        search_term=stv.search_term,
                        ad_group_id=ag_id,
                        impressions=m.impressions,
                        clicks=m.clicks,
                        cost_micros=m.cost_micros,
                        conversions=m.conversions,
                        matched_keyword_id=None,
                    )
                )
        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def query_ads(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[AdSnapshot]:
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    date_str = snapshot_date.isoformat()
    query = f"""
        SELECT
            ad_group_ad.ad.id,
            ad_group_ad.ad_group,
            ad_group_ad.ad.type,
            ad_group_ad.status,
            ad_group_ad.ad.responsive_search_ad.headlines,
            ad_group_ad.ad.responsive_search_ad.descriptions,
            ad_group_ad.ad.final_urls,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM ad_group_ad
        WHERE segments.date = '{date_str}'
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[AdSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                aga = row.ad_group_ad
                ad = aga.ad
                m = row.metrics
                ag_resource = aga.ad_group
                ag_id = int(ag_resource.split("/")[-1]) if ag_resource else 0

                rsa = ad.responsive_search_ad
                headlines = [h.text for h in rsa.headlines] if rsa else []
                descriptions = [d.text for d in rsa.descriptions] if rsa else []
                final_urls = list(ad.final_urls)

                results.append(
                    AdSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=snapshot_date,
                        ad_id=ad.id,
                        ad_group_id=ag_id,
                        type=ad.type_.name if hasattr(ad, "type_") else "",
                        status=aga.status.name,
                        headlines_json=json.dumps(headlines),
                        descriptions_json=json.dumps(descriptions),
                        final_urls_json=json.dumps(final_urls),
                        impressions=m.impressions,
                        clicks=m.clicks,
                        cost_micros=m.cost_micros,
                        conversions=m.conversions,
                    )
                )
        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc
