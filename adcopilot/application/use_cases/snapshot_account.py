"""SnapshotAccountUseCase — pulls a full daily snapshot for one account."""

import asyncio
import dataclasses
import time
from dataclasses import dataclass
from datetime import date

import sentry_sdk
import structlog

from adcopilot.application.ports.google_ads import GoogleAdsClientPort
from adcopilot.application.ports.repositories import (
    GoogleAdsAccountRepository,
    OAuthCredentialsRepository,
)
from adcopilot.application.ports.snapshot_repository import SnapshotRepository
from adcopilot.application.ports.web_notifier import WebNotifier
from adcopilot.application.services.reauth_notification import build_reauth_notification
from adcopilot.domain.entities import AccountId
from adcopilot.domain.exceptions import GoogleAdsAuthError

logger = structlog.get_logger(__name__)


@dataclass
class SnapshotResult:
    account_id: AccountId
    snapshot_date: date
    campaigns: int
    ad_groups: int
    keywords: int
    search_terms: int
    ads: int
    negative_keywords: int
    duration_seconds: float
    success: bool = True
    error_message: str | None = None


class SnapshotAccountUseCase:
    def __init__(
        self,
        ads_client: GoogleAdsClientPort,
        snapshot_repo: SnapshotRepository,
        credentials_repo: OAuthCredentialsRepository,
        account_repo: GoogleAdsAccountRepository,
        web_notifier: WebNotifier | None = None,
    ) -> None:
        self._ads_client = ads_client
        self._snapshot_repo = snapshot_repo
        self._credentials_repo = credentials_repo
        self._account_repo = account_repo
        self._web_notifier = web_notifier

    async def execute(self, account_id: AccountId, snapshot_date: date) -> SnapshotResult:
        from adcopilot.observability import set_account_context

        set_account_context(account_id)
        with sentry_sdk.start_transaction(
            op="snapshot.execute",
            name="SnapshotAccountUseCase.execute",
        ) as txn:
            txn.set_tag("account_id", account_id)
            txn.set_tag("snapshot_date", snapshot_date.isoformat())
            return await self._execute_inner(account_id, snapshot_date)

    async def _mark_needs_reauth(self, account) -> None:  # type: ignore[no-untyped-def]
        """Flag the account for reauth and emit a one-time REAUTH_REQUIRED
        notification on the False→True transition."""
        was_flagged = account.needs_reauth
        await self._account_repo.save(dataclasses.replace(account, needs_reauth=True))
        if self._web_notifier is not None and not was_flagged:
            title, body, metadata = build_reauth_notification(account)
            await self._web_notifier.send_reauth_required(
                user_id=str(account.user_id),
                title=title,
                body=body,
                metadata=metadata,
            )

    async def _execute_inner(self, account_id: AccountId, snapshot_date: date) -> SnapshotResult:
        start = time.monotonic()

        # 1. Load account
        account = await self._account_repo.get(account_id)
        if account is None:
            return SnapshotResult(
                account_id=account_id,
                snapshot_date=snapshot_date,
                campaigns=0,
                ad_groups=0,
                keywords=0,
                search_terms=0,
                ads=0,
                negative_keywords=0,
                duration_seconds=time.monotonic() - start,
                success=False,
                error_message="Account not found",
            )

        # 2. Load credentials
        creds = await self._credentials_repo.get(account_id)
        if creds is None:
            return SnapshotResult(
                account_id=account_id,
                snapshot_date=snapshot_date,
                campaigns=0,
                ad_groups=0,
                keywords=0,
                search_terms=0,
                ads=0,
                negative_keywords=0,
                duration_seconds=time.monotonic() - start,
                success=False,
                error_message="No credentials found",
            )

        refresh_token = creds.refresh_token
        customer_id = account.customer_id

        # 3. Pull all 14 entity types in parallel
        try:
            fetch_span = sentry_sdk.start_span(op="snapshot.fetch", name="google_ads.fetch_all")
            (
                campaigns,
                ad_groups,
                keywords,
                search_terms,
                ads,
                negative_keywords,
                device_performance,
                geo_performance,
                hour_performance,
                day_of_week_performance,
                audience_performance,
                conversion_actions,
                campaign_extensions,
                sitelink_performance,
            ) = await asyncio.gather(
                self._ads_client.query_campaigns(refresh_token, customer_id, snapshot_date),
                self._ads_client.query_ad_groups(refresh_token, customer_id, snapshot_date),
                self._ads_client.query_keywords(refresh_token, customer_id, snapshot_date),
                self._ads_client.query_search_terms(refresh_token, customer_id, snapshot_date),
                self._ads_client.query_ads(refresh_token, customer_id, snapshot_date),
                self._ads_client.query_negative_keywords(refresh_token, customer_id, snapshot_date),
                self._ads_client.query_device_performance(
                    refresh_token, customer_id, snapshot_date
                ),
                self._ads_client.query_geo_performance(refresh_token, customer_id, snapshot_date),
                self._ads_client.query_hour_performance(refresh_token, customer_id, snapshot_date),
                self._ads_client.query_day_of_week_performance(
                    refresh_token, customer_id, snapshot_date
                ),
                self._ads_client.query_audience_performance(
                    refresh_token, customer_id, snapshot_date
                ),
                self._ads_client.query_conversion_actions(
                    refresh_token, customer_id, snapshot_date
                ),
                self._ads_client.query_campaign_extensions(
                    refresh_token, customer_id, snapshot_date
                ),
                self._ads_client.query_sitelink_performance(
                    refresh_token, customer_id, snapshot_date
                ),
            )
            fetch_span.finish()
        except GoogleAdsAuthError as exc:
            logger.warning(
                "google ads auth error during snapshot",
                account_id=account_id,
                error=str(exc),
            )
            # Mark account as needing re-auth.  Notify the user only on the
            # first transition into the needs_reauth state so repeated nightly
            # failures don't spam the bell until they reconnect.
            await self._mark_needs_reauth(account)
            return SnapshotResult(
                account_id=account_id,
                snapshot_date=snapshot_date,
                campaigns=0,
                ad_groups=0,
                keywords=0,
                search_terms=0,
                ads=0,
                negative_keywords=0,
                duration_seconds=time.monotonic() - start,
                success=False,
                error_message=f"GoogleAdsAuthError: {exc}",
            )

        # 4. Upsert all in one transaction — callers are responsible for session scope,
        #    but we flush after each upsert batch and expect a single outer transaction.
        upsert_span = sentry_sdk.start_span(op="snapshot.upsert", name="snapshot.upsert_all")
        await self._snapshot_repo.upsert_campaigns(account_id, campaigns)
        await self._snapshot_repo.upsert_ad_groups(account_id, ad_groups)
        await self._snapshot_repo.upsert_keywords(account_id, keywords)
        await self._snapshot_repo.upsert_search_terms(account_id, search_terms)
        await self._snapshot_repo.upsert_ads(account_id, ads)
        await self._snapshot_repo.upsert_negative_keywords(account_id, negative_keywords)
        await self._snapshot_repo.upsert_device_performance(account_id, device_performance)
        await self._snapshot_repo.upsert_geo_performance(account_id, geo_performance)
        await self._snapshot_repo.upsert_hour_performance(account_id, hour_performance)
        await self._snapshot_repo.upsert_day_of_week_performance(
            account_id, day_of_week_performance
        )
        await self._snapshot_repo.upsert_audience_performance(account_id, audience_performance)
        await self._snapshot_repo.upsert_conversion_actions(account_id, conversion_actions)
        await self._snapshot_repo.upsert_campaign_extensions(account_id, campaign_extensions)
        await self._snapshot_repo.upsert_sitelink_performance(account_id, sitelink_performance)
        upsert_span.finish()

        duration = time.monotonic() - start
        logger.info(
            "snapshot complete",
            account_id=account_id,
            date=snapshot_date.isoformat(),
            campaigns=len(campaigns),
            ad_groups=len(ad_groups),
            keywords=len(keywords),
            search_terms=len(search_terms),
            ads=len(ads),
            negative_keywords=len(negative_keywords),
            device_performance=len(device_performance),
            geo_performance=len(geo_performance),
            hour_performance=len(hour_performance),
            day_of_week_performance=len(day_of_week_performance),
            audience_performance=len(audience_performance),
            conversion_actions=len(conversion_actions),
            campaign_extensions=len(campaign_extensions),
            sitelink_performance=len(sitelink_performance),
            duration_seconds=round(duration, 2),
        )

        return SnapshotResult(
            account_id=account_id,
            snapshot_date=snapshot_date,
            campaigns=len(campaigns),
            ad_groups=len(ad_groups),
            keywords=len(keywords),
            search_terms=len(search_terms),
            ads=len(ads),
            negative_keywords=len(negative_keywords),
            duration_seconds=duration,
        )
