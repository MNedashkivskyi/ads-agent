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
    RemarketingListInfo,
    SearchTermSnapshot,
    SitelinkPerformanceSnapshot,
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
    from adcopilot.infrastructure.google_ads.client import is_google_auth_error

    if is_google_auth_error(exc):
        return GoogleAdsAuthError(str(exc))
    error_str = str(exc).lower()
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
            metrics.conversions_value,
            metrics.search_impression_share,
            metrics.search_budget_lost_impression_share,
            metrics.search_rank_lost_impression_share,
            campaign.target_cpa.target_cpa_micros,
            metrics.all_conversions
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

                def _is_metric(v: float) -> float | None:
                    """Return None for sentinel values Google uses when a metric is unavailable."""
                    return None if v in (0.0, float("inf")) else v

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
                        search_impression_share=_is_metric(m.search_impression_share),
                        search_budget_lost_impression_share=_is_metric(
                            m.search_budget_lost_impression_share
                        ),
                        search_rank_lost_impression_share=_is_metric(
                            m.search_rank_lost_impression_share
                        ),
                        target_cpa_micros=c.target_cpa.target_cpa_micros or None,
                        all_conversions=m.all_conversions,
                    )
                )
        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def query_conversion_actions(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[ConversionActionSnapshot]:
    """Fetch all non-removed conversion action configurations for an account.

    Conversion actions are account-level configuration (not daily metrics).
    We store them with the snapshot_date so history is preserved.
    """
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    query = """
        SELECT
            conversion_action.id,
            conversion_action.name,
            conversion_action.category,
            conversion_action.counting_type,
            conversion_action.status,
            conversion_action.include_in_conversions_metric
        FROM conversion_action
        WHERE conversion_action.status != 'REMOVED'
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[ConversionActionSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                ca = row.conversion_action
                results.append(
                    ConversionActionSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=snapshot_date,
                        conversion_action_id=ca.id,
                        name=ca.name,
                        category=ca.category.name,
                        counting_type=ca.counting_type.name,
                        status=ca.status.name,
                        include_in_conversions_metric=ca.include_in_conversions_metric,
                    )
                )
        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def list_conversion_actions(
    refresh_token: str,
    customer_id: str,
    settings: Settings,
) -> list[ConversionActionSnapshot]:
    """Fetch all conversion actions with 7-day all_conversions metric.

    Uses a single GAQL query with a 7-day date range (CCR-1).
    Returns an empty list for accounts with zero conversion actions.
    """
    from datetime import datetime, timedelta, timezone

    today = datetime.now(timezone.utc).date()
    seven_days_ago = today - timedelta(days=7)
    date_range = f"'{seven_days_ago}' AND '{today}'"

    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    query = f"""
        SELECT
            conversion_action.id,
            conversion_action.name,
            conversion_action.category,
            conversion_action.counting_type,
            conversion_action.status,
            conversion_action.include_in_conversions_metric,
            metrics.all_conversions
        FROM conversion_action
        WHERE segments.date BETWEEN {date_range}
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[ConversionActionSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                ca = row.conversion_action
                results.append(
                    ConversionActionSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=today,
                        conversion_action_id=ca.id,
                        name=ca.name,
                        category=ca.category.name,
                        counting_type=ca.counting_type.name,
                        status=ca.status.name,
                        include_in_conversions_metric=ca.include_in_conversions_metric,
                        all_conversions=float(row.metrics.all_conversions),
                    )
                )
        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def list_recent_search_terms(
    refresh_token: str,
    customer_id: str,
    settings: Settings,
    days: int = 7,
    limit: int = 20,
) -> list[SearchTermSnapshot]:
    """Fetch top search terms by cost for the last *days* days (CCR-1: single bounded query).

    Results are ordered by cost_micros descending, capped at *limit* rows.
    Returns an empty list for accounts with no search term data.
    """
    from datetime import datetime, timedelta, timezone

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days)
    date_range = f"'{start}' AND '{today}'"

    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    query = f"""
        SELECT
            search_term_view.search_term,
            campaign.name,
            metrics.cost_micros,
            metrics.clicks,
            metrics.impressions,
            metrics.conversions
        FROM search_term_view
        WHERE segments.date BETWEEN {date_range}
        ORDER BY metrics.cost_micros DESC
        LIMIT {limit}
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
                results.append(
                    SearchTermSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=today,
                        search_term=stv.search_term,
                        ad_group_id=0,
                        impressions=m.impressions,
                        clicks=m.clicks,
                        cost_micros=m.cost_micros,
                        conversions=m.conversions,
                        matched_keyword_id=None,
                        campaign_name=row.campaign.name,
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
            ad_group_criterion.quality_info.search_predicted_ctr,
            ad_group_criterion.quality_info.creative_quality_score,
            ad_group_criterion.quality_info.post_click_quality_score,
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
                qi = agc.quality_info
                qs = qi.quality_score
                # Extract ad_group_id from resource name customers/{cid}/adGroups/{id}
                ag_resource = agc.ad_group
                ag_id = int(ag_resource.split("/")[-1]) if ag_resource else 0

                def _qs_enum(val: object) -> str | None:
                    name = getattr(val, "name", None)
                    return name if name and name != "UNKNOWN" else None

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
                        expected_ctr=_qs_enum(qi.search_predicted_ctr),
                        ad_relevance=_qs_enum(qi.creative_quality_score),
                        landing_page_experience=_qs_enum(qi.post_click_quality_score),
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
            ad_group_ad.ad_strength,
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

                # ad_strength is an enum; convert to name string, None for UNSPECIFIED/UNKNOWN
                strength_val = aga.ad_strength.name if hasattr(aga, "ad_strength") else None
                ad_strength = (
                    None
                    if strength_val in (None, "UNSPECIFIED", "UNKNOWN", "PENDING", "NO_ADS", "")
                    else strength_val
                )

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
                        ad_strength=ad_strength,
                    )
                )
        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def query_negative_keywords(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[NegativeKeywordSnapshot]:
    """Fetch campaign-level and ad-group-level negative keywords."""
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    results: list[NegativeKeywordSnapshot] = []

    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")

        # --- Campaign-level negatives ---
        campaign_neg_query = """
            SELECT
                campaign_criterion.criterion_id,
                campaign.id,
                campaign_criterion.keyword.text,
                campaign_criterion.keyword.match_type
            FROM campaign_criterion
            WHERE campaign_criterion.type = 'KEYWORD'
              AND campaign_criterion.negative = TRUE
        """
        try:
            stream = service.search_stream(customer_id=cid, query=campaign_neg_query)
            for batch in stream:
                for row in batch.results:
                    cc = row.campaign_criterion
                    results.append(
                        NegativeKeywordSnapshot(
                            id=_make_id(),
                            account_id=account_id,
                            snapshot_date=snapshot_date,
                            criterion_id=cc.criterion_id,
                            campaign_id=row.campaign.id,
                            ad_group_id=0,
                            text=cc.keyword.text,
                            match_type=cc.keyword.match_type.name,
                        )
                    )
        except Exception as exc:
            logger.warning("failed to fetch campaign-level negative keywords", error=str(exc))

        # --- Ad-group-level negatives ---
        ag_neg_query = """
            SELECT
                ad_group_criterion.criterion_id,
                ad_group_criterion.ad_group,
                campaign.id,
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type
            FROM ad_group_criterion
            WHERE ad_group_criterion.type = 'KEYWORD'
              AND ad_group_criterion.negative = TRUE
        """
        try:
            stream = service.search_stream(customer_id=cid, query=ag_neg_query)
            for batch in stream:
                for row in batch.results:
                    agc = row.ad_group_criterion
                    ag_resource = agc.ad_group
                    ag_id = int(ag_resource.split("/")[-1]) if ag_resource else 0
                    results.append(
                        NegativeKeywordSnapshot(
                            id=_make_id(),
                            account_id=account_id,
                            snapshot_date=snapshot_date,
                            criterion_id=agc.criterion_id,
                            campaign_id=row.campaign.id,
                            ad_group_id=ag_id,
                            text=agc.keyword.text,
                            match_type=agc.keyword.match_type.name,
                        )
                    )
        except Exception as exc:
            logger.warning(
                "failed to fetch ad-group-level negative keywords", error=str(exc)
            )

        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def query_device_performance(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[DevicePerformanceSnapshot]:
    """Fetch daily performance metrics segmented by device type."""
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    date_str = snapshot_date.isoformat()
    query = f"""
        SELECT
            campaign.id,
            segments.device,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM campaign
        WHERE segments.date = '{date_str}'
          AND segments.device != 'UNSPECIFIED'
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[DevicePerformanceSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                m = row.metrics
                device = row.segments.device.name
                if device in ("UNSPECIFIED", "UNKNOWN"):
                    continue
                results.append(
                    DevicePerformanceSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=snapshot_date,
                        campaign_id=row.campaign.id,
                        device=device,
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


async def query_geo_performance(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[GeoPerformanceSnapshot]:
    """Fetch daily performance metrics segmented by geographic location."""
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    date_str = snapshot_date.isoformat()
    query = f"""
        SELECT
            campaign.id,
            geographic_view.country_criterion_id,
            geographic_view.location_type,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM geographic_view
        WHERE segments.date = '{date_str}'
          AND geographic_view.location_type = 'LOCATION_OF_PRESENCE'
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[GeoPerformanceSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                m = row.metrics
                location_id = row.geographic_view.country_criterion_id
                if not location_id:
                    continue
                results.append(
                    GeoPerformanceSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=snapshot_date,
                        campaign_id=row.campaign.id,
                        location_id=int(location_id),
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


async def query_hour_performance(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[HourPerformanceSnapshot]:
    """Fetch daily performance metrics segmented by hour of day (0-23)."""
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    date_str = snapshot_date.isoformat()
    query = f"""
        SELECT
            campaign.id,
            segments.hour_of_day,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM campaign
        WHERE segments.date = '{date_str}'
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[HourPerformanceSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                m = row.metrics
                results.append(
                    HourPerformanceSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=snapshot_date,
                        campaign_id=row.campaign.id,
                        hour_of_day=int(row.segments.hour_of_day),
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


async def query_campaign_extensions(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[CampaignExtensionSnapshot]:
    """Fetch which extension types are attached to each campaign.

    Queries ``campaign_extension_setting`` for SITELINK, CALLOUT, and
    STRUCTURED_SNIPPET extension types.  Returns one snapshot per
    (campaign, extension_type) pair so that rules 41–43 can cheaply check
    whether a campaign is missing a given extension.
    """
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    query = """
        SELECT
            campaign.id,
            campaign_extension_setting.extension_type
        FROM campaign_extension_setting
        WHERE campaign_extension_setting.extension_type IN (
            'SITELINK', 'CALLOUT', 'STRUCTURED_SNIPPET'
        )
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[CampaignExtensionSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                ext_type = row.campaign_extension_setting.extension_type.name
                if ext_type in ("UNSPECIFIED", "UNKNOWN"):
                    continue
                results.append(
                    CampaignExtensionSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=snapshot_date,
                        campaign_id=row.campaign.id,
                        extension_type=ext_type,
                    )
                )
        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def query_sitelink_performance(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[SitelinkPerformanceSnapshot]:
    """Fetch daily click + impression metrics for sitelink assets per campaign.

    Queries ``campaign_asset`` filtered to SITELINK assets for a single day.
    Rule 44 loads a 30-day window of these snapshots from the DB, aggregates
    by asset_id, and flags low-performing sitelinks (CTR < 0.5%, ≥500
    impressions).
    """
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    date_str = snapshot_date.isoformat()
    query = f"""
        SELECT
            campaign.id,
            asset.id,
            metrics.impressions,
            metrics.clicks
        FROM campaign_asset
        WHERE asset.type = 'SITELINK'
          AND segments.date = '{date_str}'
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[SitelinkPerformanceSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                m = row.metrics
                results.append(
                    SitelinkPerformanceSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=snapshot_date,
                        campaign_id=row.campaign.id,
                        asset_id=row.asset.id,
                        impressions=m.impressions,
                        clicks=m.clicks,
                    )
                )
        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def query_day_of_week_performance(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[DayOfWeekPerformanceSnapshot]:
    """Fetch daily performance metrics segmented by day of week."""
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    date_str = snapshot_date.isoformat()
    query = f"""
        SELECT
            campaign.id,
            segments.day_of_week,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM campaign
        WHERE segments.date = '{date_str}'
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[DayOfWeekPerformanceSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                m = row.metrics
                day = row.segments.day_of_week.name
                if day in ("UNSPECIFIED", "UNKNOWN"):
                    continue
                results.append(
                    DayOfWeekPerformanceSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=snapshot_date,
                        campaign_id=row.campaign.id,
                        day_of_week=day,
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


async def query_audience_performance(
    refresh_token: str,
    customer_id: str,
    snapshot_date: date,
    settings: Settings,
) -> list[AudiencePerformanceSnapshot]:
    """Fetch daily performance for observation audiences in ad groups."""
    cid = customer_id.replace("-", "")
    account_id = AccountId(customer_id)
    date_str = snapshot_date.isoformat()
    query = f"""
        SELECT
            campaign.id,
            ad_group.id,
            ad_group_criterion.criterion_id,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM ad_group_audience_view
        WHERE segments.date = '{date_str}'
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[AudiencePerformanceSnapshot] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                m = row.metrics
                results.append(
                    AudiencePerformanceSnapshot(
                        id=_make_id(),
                        account_id=account_id,
                        snapshot_date=snapshot_date,
                        campaign_id=row.campaign.id,
                        ad_group_id=row.ad_group.id,
                        criterion_id=row.ad_group_criterion.criterion_id,
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


async def query_remarketing_lists(
    refresh_token: str,
    customer_id: str,
    settings: Settings,
) -> list[RemarketingListInfo]:
    """Fetch user list (remarketing audience) info for an account.

    Returns all OPEN lists — used to check tag status and RLSA eligibility.
    member_count is -1 when the list is under the minimum size threshold.
    """
    cid = customer_id.replace("-", "")
    query = """
        SELECT
            user_list.id,
            user_list.name,
            user_list.membership_status,
            user_list.size_for_search
        FROM user_list
        WHERE user_list.membership_status = 'OPEN'
        ORDER BY user_list.id
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[RemarketingListInfo] = []
        stream = service.search_stream(customer_id=cid, query=query)
        for batch in stream:
            for row in batch.results:
                ul = row.user_list
                results.append(
                    RemarketingListInfo(
                        list_id=ul.id,
                        name=ul.name,
                        member_count=ul.size_for_search if ul.size_for_search >= 0 else -1,
                        status=ul.membership_status.name,
                    )
                )
        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def fetch_ad_metrics(
    refresh_token: str,
    customer_id: str,
    ad_resource_name: str,
    settings: Settings,
    days: int = 7,
) -> dict:
    """Return impressions, clicks, and conversions for a specific ad over the last N days."""
    query = f"""
        SELECT
            ad_group_ad.resource_name,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions
        FROM ad_group_ad
        WHERE ad_group_ad.resource_name = '{ad_resource_name}'
          AND segments.date DURING LAST_{days}_DAYS
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        impressions = clicks = conversions = 0.0
        stream = service.search_stream(customer_id=customer_id.replace("-", ""), query=query)
        for batch in stream:
            for row in batch.results:
                impressions += row.metrics.impressions
                clicks += row.metrics.clicks
                conversions += row.metrics.conversions
        return {
            "impressions": impressions,
            "clicks": clicks,
            "conversions": conversions,
        }
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def query_merchant_center_feed(
    refresh_token: str,
    customer_id: str,
    settings: Settings,
) -> list[dict[str, object]]:
    """Return a list of linked Merchant Center feeds for the account.

    Each dict contains: ``feed_id`` (int), ``name`` (str), ``status`` (str).
    Returns an empty list when no Merchant Center feed is linked.

    Uses the ``MerchantCenterLink`` resource which is available without
    special permissions — just the regular Google Ads API access.
    """
    query = """
        SELECT
            merchant_center_link.id,
            merchant_center_link.merchant_center_account_name,
            merchant_center_link.status
        FROM merchant_center_link
    """
    try:
        client = _build_client(refresh_token, settings)
        service = client.get_service("GoogleAdsService")
        results: list[dict[str, object]] = []
        stream = service.search_stream(customer_id=customer_id, query=query)
        for batch in stream:
            for row in batch.results:
                link = row.merchant_center_link
                results.append(
                    {
                        "feed_id": link.id,
                        "name": link.merchant_center_account_name or "",
                        "status": link.status.name if hasattr(link.status, "name") else str(link.status),
                    }
                )
        return results
    except (GoogleAdsAuthError, GoogleAdsUnavailable):
        raise
    except Exception as exc:
        raise _wrap_exc(exc) from exc


async def fetch_auction_insights(
    refresh_token: str,
    customer_id: str,
    settings: "Settings",
    snapshot_date: "date",
) -> list[dict]:
    """Fetch Auction Insights report for all enabled campaigns.

    Returns a list of dicts with keys:
        campaign_id, competitor_domain, impression_share, overlap_rate, position_above_rate
    """
    from datetime import date as _date
    import asyncio

    def _sync() -> list[dict]:
        client = _build_client(refresh_token, customer_id, settings)
        service = client.get_service("GoogleAdsService")
        query = """
            SELECT
                campaign.id,
                auction_insight.domain,
                metrics.auction_insight_search_impression_share,
                metrics.auction_insight_search_overlap_rate,
                metrics.auction_insight_search_position_above_rate
            FROM auction_insight
            WHERE campaign.status = 'ENABLED'
              AND segments.date DURING LAST_7_DAYS
        """
        results = []
        try:
            response = service.search(customer_id=customer_id, query=query)
            for row in response:
                results.append({
                    "campaign_id": row.campaign.id,
                    "competitor_domain": row.auction_insight.domain,
                    "impression_share": row.metrics.auction_insight_search_impression_share or None,
                    "overlap_rate": row.metrics.auction_insight_search_overlap_rate or None,
                    "position_above_rate": row.metrics.auction_insight_search_position_above_rate or None,
                })
        except Exception as exc:
            raise _wrap_exc(exc) from exc
        return results

    return await asyncio.get_event_loop().run_in_executor(None, _sync)
