"""RunDetection use case: loads snapshot, builds context, runs rule engine."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import sentry_sdk
import structlog

from adcopilot.application.detection.base import DetectionContext, HistoricalStats, LandingPageData
from adcopilot.application.detection.engine import RuleEngine
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.application.ports.repositories import GoogleAdsAccountRepository
from adcopilot.application.ports.snapshot_repository import SnapshotData, SnapshotRepository
from adcopilot.domain.entities import AccountId
from adcopilot.domain.polish_market.attribution_windows import attribution_window_days
from adcopilot.domain.recommendation import RecommendationSeverity

logger = structlog.get_logger(__name__)

_TREND_LOOKBACK_DAYS = 7
_DEVICE_LOOKBACK_DAYS = 7
_GEO_LOOKBACK_DAYS = 30
_HOUR_LOOKBACK_DAYS = 30
_DOW_LOOKBACK_DAYS = 30
_SITELINK_LOOKBACK_DAYS = 30


class RunDetectionUseCase:
    def __init__(
        self,
        snapshot_repo: SnapshotRepository,
        rec_repo: RecommendationRepository,
        rule_engine: RuleEngine,
        account_repo: GoogleAdsAccountRepository,
        economics_repo: Any | None = None,
        spend_safety_repo: Any | None = None,
    ) -> None:
        self._snapshot_repo = snapshot_repo
        self._rec_repo = rec_repo
        self._engine = rule_engine
        self._account_repo = account_repo
        self._economics_repo = economics_repo
        self._spend_safety_repo = spend_safety_repo

    async def execute(self, account_id: AccountId, snapshot_date: date) -> dict[str, int]:
        """Run detection for one account on one snapshot date.

        Returns a count dict keyed by severity name, e.g. {'CRITICAL': 2, 'HIGH': 5}.
        """
        from adcopilot.observability import set_account_context

        set_account_context(account_id)
        with sentry_sdk.start_transaction(
            op="detection.run",
            name="RunDetectionUseCase.execute",
        ) as txn:
            txn.set_tag("account_id", account_id)
            txn.set_tag("snapshot_date", snapshot_date.isoformat())
            return await self._execute_inner(account_id, snapshot_date)

    async def _execute_inner(self, account_id: AccountId, snapshot_date: date) -> dict[str, int]:
        # 1. Load account entity
        account = await self._account_repo.get(account_id)
        if account is None:
            logger.warning("account not found, skipping detection", account_id=account_id)
            return {}

        # 2. Load current snapshot data
        snapshot = await self._snapshot_repo.load_snapshot(account_id, snapshot_date)

        # 2b. Drop campaigns that have been removed in Google Ads (and all their
        #     child entities). The snapshot still records them with status
        #     REMOVED, but detection must never produce recommendations for a
        #     deleted campaign. Combined with the rule engine's reconciliation
        #     pass, any previously-created recs for these campaigns are expired.
        snapshot = _exclude_removed_campaigns(snapshot)

        # 3. Load 7-day-ago snapshots for trend-based rules (Modules 1 & 2).
        #    These are best-effort — if no data exists the lists stay empty and
        #    trend rules simply skip (they check for empty prev_* lists).
        prev_date = snapshot_date - timedelta(days=_TREND_LOOKBACK_DAYS)
        prev_campaigns, prev_ad_groups, prev_keywords, prev_ads = await _load_prev_snapshots(
            self._snapshot_repo, account_id, prev_date
        )

        # 3b. Load targeting dimension data for Module 4 rules (best-effort).
        (
            device_performance,
            geo_performance,
            hour_performance,
            day_of_week_performance,
            audience_performance,
        ) = await _load_targeting_performance(self._snapshot_repo, account_id, snapshot_date)

        # 3c. Load conversion action configuration for Module 6 rules (best-effort).
        try:
            conversion_actions = await self._snapshot_repo.get_conversion_actions(
                account_id, snapshot_date
            )
        except Exception:
            conversion_actions = []

        # 3d. Load ad extension data for Module 7 rules (best-effort).
        campaign_extensions, sitelink_performance = await _load_extension_data(
            self._snapshot_repo, account_id, snapshot_date
        )

        # 3d-bis. Load business economics for value-based rules (rule 40, best-effort).
        spend_safety_config = None
        if self._spend_safety_repo is not None:
            try:
                spend_safety_config = await self._spend_safety_repo.get(str(account_id))
            except Exception:
                spend_safety_config = None

        business_economics = None
        if self._economics_repo is not None:
            try:
                business_economics = await self._economics_repo.get(str(account_id))
            except Exception:
                business_economics = None

        # Vertical drives the conversion-attribution window for lag-sensitive
        # rules. Best-effort: derive from whatever vertical signal is available
        # (business economics today; a per-account vertical field once wired).
        # Falls back to the default window when unknown.
        vertical = getattr(business_economics, "vertical", None) or getattr(
            account, "vertical", None
        )
        attribution_window = attribution_window_days(vertical)

        # 4. Compute HistoricalStats from the snapshot itself (30-day proxy)
        total_cost = sum(c.cost_micros for c in snapshot.campaigns)
        total_conversions = sum(c.conversions for c in snapshot.campaigns)
        avg_cpa = int(total_cost / total_conversions) if total_conversions > 0 else 0
        history = HistoricalStats(
            avg_cpa_micros=avg_cpa,
            total_cost_micros=total_cost,
            total_conversions=total_conversions,
            days=30,
        )

        # 3e. Pre-fetch landing pages for Rule 45 (best-effort, non-blocking)
        landing_page_results = await _fetch_landing_pages(snapshot.ads)

        # 3f. Load GA4 page metrics if available (best-effort)
        ga4_page_metrics = await _load_ga4_metrics(
            str(account_id), snapshot_date, self._snapshot_repo
        )

        # 3g. Load 14-day auction insights for competitive rules (best-effort)
        try:
            auction_insights = await self._snapshot_repo.get_auction_insights(
                account_id,
                snapshot_date - timedelta(days=14),
                snapshot_date,
            )
        except Exception:
            auction_insights = []

        # 3h. Load PMax/Shopping asset groups + listing-group filters (best-effort)
        try:
            asset_groups = await self._snapshot_repo.load_asset_groups(account_id, snapshot_date)
        except Exception:
            asset_groups = []
        try:
            listing_groups = await self._snapshot_repo.load_listing_groups(
                account_id, snapshot_date
            )
        except Exception:
            listing_groups = []

        # 5. Build context
        ctx = DetectionContext(
            account=account,
            campaigns=snapshot.campaigns,
            ad_groups=snapshot.ad_groups,
            keywords=snapshot.keywords,
            search_terms=snapshot.search_terms,
            ads=snapshot.ads,
            history=history,
            snapshot_date=snapshot_date,
            prev_campaigns=prev_campaigns,
            prev_ad_groups=prev_ad_groups,
            prev_keywords=prev_keywords,
            prev_ads=prev_ads,
            negative_keywords=snapshot.negative_keywords,
            device_performance=device_performance,
            geo_performance=geo_performance,
            hour_performance=hour_performance,
            day_of_week_performance=day_of_week_performance,
            audience_performance=audience_performance,
            conversion_actions=conversion_actions,
            campaign_extensions=campaign_extensions,
            sitelink_performance=sitelink_performance,
            landing_page_results=landing_page_results,
            ga4_page_metrics=ga4_page_metrics,
            auction_insights=auction_insights,
            business_economics=business_economics,
            spend_safety_config=spend_safety_config,
            asset_groups=asset_groups,
            listing_groups=listing_groups,
            vertical=vertical,
            attribution_window_days=attribution_window,
        )

        # 6. Run rule engine
        with sentry_sdk.start_span(op="detection.engine", name="RuleEngine.run"):
            new_recs = await self._engine.run(ctx)

        # 7. Aggregate by severity
        counts: dict[str, int] = {s.value: 0 for s in RecommendationSeverity}
        for rec in new_recs:
            counts[rec.severity.value] += 1

        logger.info(
            "detection complete",
            account_id=account_id,
            date=snapshot_date.isoformat(),
            new_recommendations=len(new_recs),
            by_severity=counts,
        )
        return counts


def _exclude_removed_campaigns(snapshot: SnapshotData) -> SnapshotData:
    """Return the snapshot with REMOVED campaigns and their children stripped.

    A campaign deleted in Google Ads is still returned by the snapshot query
    (with status REMOVED) so its row is kept up to date, but it must not drive
    any recommendations. We also drop the ad groups, keywords, search terms,
    ads and negative keywords that belong to those campaigns so no child-level
    rule fires on a dead campaign either.
    """
    removed_ids = {
        c.campaign_id for c in snapshot.campaigns if (c.status or "").upper() == "REMOVED"
    }
    if not removed_ids:
        return snapshot

    live_ad_groups = [ag for ag in snapshot.ad_groups if ag.campaign_id not in removed_ids]
    live_ag_ids = {ag.ad_group_id for ag in live_ad_groups}

    snapshot.campaigns = [c for c in snapshot.campaigns if c.campaign_id not in removed_ids]
    snapshot.ad_groups = live_ad_groups
    snapshot.keywords = [k for k in snapshot.keywords if k.ad_group_id in live_ag_ids]
    snapshot.search_terms = [s for s in snapshot.search_terms if s.ad_group_id in live_ag_ids]
    snapshot.ads = [a for a in snapshot.ads if a.ad_group_id in live_ag_ids]
    snapshot.negative_keywords = [
        n
        for n in snapshot.negative_keywords
        if n.campaign_id not in removed_ids and (n.ad_group_id == 0 or n.ad_group_id in live_ag_ids)
    ]

    logger.info("excluded removed campaigns from detection", removed_campaigns=len(removed_ids))
    return snapshot


async def _load_targeting_performance(
    snapshot_repo: SnapshotRepository,
    account_id: AccountId,
    snapshot_date: date,
) -> tuple[list, list, list, list, list]:
    """Load targeting dimension data for Module 4 rules (best-effort).

    Uses a 30-day window for geo/hour/day-of-week (statistical stability)
    and a 7-day window for device performance.  Returns five empty lists on
    any failure so that a missing dimension never blocks detection.
    """
    try:
        end_date = snapshot_date
        start_date_30d = snapshot_date - timedelta(days=29)
        start_date_7d = snapshot_date - timedelta(days=6)
        device = await snapshot_repo.get_device_performance(account_id, start_date_7d, end_date)
        geo = await snapshot_repo.get_geo_performance(account_id, start_date_30d, end_date)
        hour = await snapshot_repo.get_hour_performance(account_id, start_date_30d, end_date)
        dow = await snapshot_repo.get_day_of_week_performance(account_id, start_date_30d, end_date)
        audience = await snapshot_repo.get_audience_performance(account_id, snapshot_date)
        return device, geo, hour, dow, audience
    except Exception:
        return [], [], [], [], []


async def _load_extension_data(
    snapshot_repo: SnapshotRepository,
    account_id: AccountId,
    snapshot_date: date,
) -> tuple[list, list]:
    """Load ad extension data for Module 7 rules (best-effort).

    Returns (campaign_extensions, sitelink_performance).  Both lists are empty
    on any failure so a missing extension snapshot never blocks detection.
    """
    try:
        start_date = snapshot_date - timedelta(days=_SITELINK_LOOKBACK_DAYS - 1)
        extensions = await snapshot_repo.get_campaign_extensions(account_id, snapshot_date)
        sitelinks = await snapshot_repo.get_sitelink_performance(
            account_id, start_date, snapshot_date
        )
        return extensions, sitelinks
    except Exception:
        return [], []


async def _load_prev_snapshots(
    snapshot_repo: SnapshotRepository,
    account_id: AccountId,
    prev_date: date,
) -> tuple[list, list, list, list]:
    """Load campaigns, ad groups, and keywords from prev_date.

    Returns three empty lists if no data exists for that date (new accounts,
    first run, or gap in snapshots).  Errors are swallowed so a missing
    historical snapshot never blocks the current detection run.
    """
    try:
        prev_campaigns = await snapshot_repo.get_campaigns_by_date(account_id, prev_date)
        prev_ad_groups = await snapshot_repo.get_ad_groups_by_date(account_id, prev_date)
        prev_keywords = await snapshot_repo.get_keywords_by_date(account_id, prev_date)
        prev_ads = await snapshot_repo.get_ads_by_date(account_id, prev_date)
        return prev_campaigns, prev_ad_groups, prev_keywords, prev_ads
    except Exception:
        return [], [], [], []


async def _fetch_landing_pages(
    ads: list,
) -> dict[str, LandingPageData]:
    """Fetch landing page content for all unique final_urls in *ads*.

    Best-effort: any URL that times out or errors is simply omitted from the
    result dict so Rule 45 skips it rather than blocking detection.
    """
    import json as _json

    from adcopilot.infrastructure.landing_page.checker import LandingPageChecker

    urls: set[str] = set()
    for ad in ads:
        try:
            final_urls = _json.loads(ad.final_urls_json or "[]")
            if final_urls:
                urls.add(final_urls[0])
        except Exception:
            continue

    if not urls:
        return {}

    checker = LandingPageChecker()
    results: dict[str, LandingPageData] = {}
    for url in urls:
        try:
            r = await checker.check(url)
            results[url] = LandingPageData(
                url=url,
                reachable=r.reachable,
                page_title=r.page_title,
                h1_text=r.h1_text,
                body_text_sample=r.body_text_sample,
            )
        except Exception:
            logger.warning("landing_page_prefetch_failed", url=url)

    return results


async def _load_ga4_metrics(
    account_id: str,
    snapshot_date,
    snapshot_repo,
) -> dict:
    """Load GA4 page metrics from DB for the detection context (best-effort)."""
    try:
        import uuid

        from sqlalchemy import select

        from adcopilot.application.detection.base import GA4PageMetrics as GA4Metrics
        from adcopilot.infrastructure.db.models import GA4PageSnapshotModel

        # snapshot_repo may not expose GA4 directly; use the underlying session
        session = getattr(snapshot_repo, "_session", None)
        if session is None:
            return {}

        result = await session.execute(
            select(GA4PageSnapshotModel).where(
                GA4PageSnapshotModel.account_id == uuid.UUID(account_id),
                GA4PageSnapshotModel.snapshot_date == snapshot_date,
            )
        )
        rows = list(result.scalars().all())
        return {
            r.page_path: GA4Metrics(
                page_path=r.page_path,
                sessions=r.sessions,
                bounce_rate=r.bounce_rate,
                avg_session_duration_sec=r.avg_session_duration_sec,
                pages_per_session=r.pages_per_session,
            )
            for r in rows
        }
    except Exception as exc:
        logger.warning("ga4_metrics_load_failed", account_id=account_id, error=str(exc))
        return {}
