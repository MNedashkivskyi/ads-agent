"""ExecuteRecommendationUseCase: runs the Google Ads mutation for an approved recommendation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import sentry_sdk
import structlog

from adcopilot.application.ports.audit_log_repository import AuditLogRepository
from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.application.ports.recommendation_executor import RecommendationExecutor
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.application.ports.repositories import (
    GoogleAdsAccountRepository,
    OAuthCredentialsRepository,
)
from adcopilot.domain.audit_log import AuditLog
from adcopilot.domain.exceptions import CampaignNotFoundError
from adcopilot.domain.recommendation import (
    RecommendationId,
    RecommendationKind,
    RecommendationStatus,
)

logger = structlog.get_logger(__name__)

_EXECUTORS: dict[RecommendationKind, RecommendationExecutor] | None = None


def _default_executors() -> dict[RecommendationKind, RecommendationExecutor]:
    from adcopilot.application.executors.ad_schedule_adjustment import AdScheduleAdjustmentExecutor
    from adcopilot.application.executors.add_callouts import AddCalloutsExecutor
    from adcopilot.application.executors.add_negative_keyword import AddNegativeKeywordExecutor
    from adcopilot.application.executors.add_sitelinks import AddSitelinksExecutor
    from adcopilot.application.executors.add_structured_snippets import (
        AddStructuredSnippetsExecutor,
    )
    from adcopilot.application.executors.adjust_bidding_strategy import (
        AdjustBiddingStrategyExecutor,
    )
    from adcopilot.application.executors.adjust_budget import AdjustBudgetExecutor
    from adcopilot.application.executors.change_match_type import ChangeMatchTypeExecutor
    from adcopilot.application.executors.device_bid_adjustment import DeviceBidAdjustmentExecutor
    from adcopilot.application.executors.geo_exclusion import GeoExclusionExecutor
    from adcopilot.application.executors.increase_budget import IncreaseBudgetExecutor
    from adcopilot.application.executors.pause_ad import PauseAdExecutor
    from adcopilot.application.executors.pause_keyword import PauseKeywordExecutor
    from adcopilot.application.executors.promote_search_term import PromoteSearchTermExecutor
    from adcopilot.application.executors.reallocate_budget import ReallocateBudgetExecutor
    from adcopilot.application.executors.refresh_ad_copy import AdCopyRefreshExecutor
    from adcopilot.application.executors.relax_target_cpa import RelaxTargetCpaExecutor
    from adcopilot.application.executors.remove_negative_conflict import (
        RemoveNegativeConflictExecutor,
    )
    from adcopilot.application.executors.remove_redundant_match_type import (
        RemoveRedundantMatchTypeExecutor,
    )
    from adcopilot.config import get_settings

    execs: list[RecommendationExecutor] = [
        PauseKeywordExecutor(),
        DeviceBidAdjustmentExecutor(),
        AdScheduleAdjustmentExecutor(),
        ReallocateBudgetExecutor(),
        RelaxTargetCpaExecutor(),
        RemoveNegativeConflictExecutor(),
        RemoveRedundantMatchTypeExecutor(),
        GeoExclusionExecutor(),
        PauseAdExecutor(),
        AddNegativeKeywordExecutor(),
        IncreaseBudgetExecutor(),
        ChangeMatchTypeExecutor(),
        AdjustBiddingStrategyExecutor(),
        AdjustBudgetExecutor(),
        AddSitelinksExecutor(),
        AddCalloutsExecutor(),
        AddStructuredSnippetsExecutor(),
        PromoteSearchTermExecutor(),
    ]
    result = {e.kind: e for e in execs}

    # Ad copy refresh — one shared executor that generates a fresh, stronger RSA
    # in the ad group. Used for every "the ad copy is weak" signal; it does not
    # delete the existing ad, so it's safe across all of these kinds.
    ad_copy_executor = AdCopyRefreshExecutor.from_settings(get_settings())
    for _kind in (
        RecommendationKind.AD_FATIGUE,
        RecommendationKind.WEAK_RSA_STRENGTH,
        RecommendationKind.ADD_AD_VARIATION,
        RecommendationKind.AD_KEYWORD_MISMATCH,
        RecommendationKind.MISSING_CTA,
        RecommendationKind.REDUNDANT_HEADLINES,
        RecommendationKind.GENERIC_DESCRIPTION,
    ):
        result[_kind] = ad_copy_executor
    return result


class ExecuteRecommendationUseCase:
    def __init__(
        self,
        rec_repo: RecommendationRepository,
        audit_log_repo: AuditLogRepository,
        account_repo: GoogleAdsAccountRepository,
        credentials_repo: OAuthCredentialsRepository,
        mutations: GoogleAdsMutationsPort,
        executors: dict[RecommendationKind, RecommendationExecutor] | None = None,
        baseline_repo: Any | None = None,
    ) -> None:
        self._rec_repo = rec_repo
        self._audit_log_repo = audit_log_repo
        self._account_repo = account_repo
        self._credentials_repo = credentials_repo
        self._mutations = mutations
        self._executors = executors if executors is not None else _default_executors()
        self._baseline_repo = baseline_repo

    async def execute(self, rec_id: RecommendationId) -> dict[str, Any]:
        with sentry_sdk.start_transaction(
            op="execute.recommendation",
            name="ExecuteRecommendationUseCase.execute",
        ) as txn:
            txn.set_tag("recommendation_id", rec_id)
            return await self._execute_inner(rec_id, txn)

    async def _execute_inner(self, rec_id: RecommendationId, txn: Any) -> dict[str, Any]:
        from adcopilot.observability import set_account_context

        rec = await self._rec_repo.get(rec_id)
        if rec is None:
            raise ValueError(f"Recommendation {rec_id} not found")
        if rec.status != RecommendationStatus.APPROVED:
            raise ValueError(f"Recommendation {rec_id} is not APPROVED (status={rec.status.value})")

        set_account_context(rec.account_id)
        txn.set_tag("account_id", rec.account_id)
        txn.set_tag("recommendation_kind", rec.kind.value)

        executor = self._executors.get(rec.kind)
        if executor is None:
            raise ValueError(f"No executor registered for {rec.kind.value}")

        account = await self._account_repo.get(rec.account_id)
        if account is None:
            raise ValueError(f"Account {rec.account_id} not found")

        credentials = await self._credentials_repo.get(rec.account_id)
        if credentials is None:
            raise ValueError(f"No OAuth credentials for account {rec.account_id}")

        # Pre-flight guard: never mutate a campaign that no longer exists.
        # The recommendation snapshot can be stale (the campaign may have been
        # removed in Google Ads after detection ran), which would otherwise fail
        # mid-mutation with "operation is not allowed for removed resources".
        campaign_id = rec.target.get("campaign_id")
        if campaign_id:
            exists = await self._mutations.campaign_exists(
                refresh_token=credentials.refresh_token,
                customer_id=account.customer_id,
                campaign_id=int(campaign_id),
            )
            if not exists:
                raise CampaignNotFoundError(
                    f"Campaign {campaign_id} no longer exists or has been removed. "
                    "This recommendation is out of date — refresh recommendations to "
                    "get up-to-date suggestions."
                )

        # One span per executor so the Sentry waterfall shows which action
        # dominated the latency (pause_keyword vs adjust_budget etc.).
        with sentry_sdk.start_span(
            op="execute.action",
            name=f"{executor.__class__.__name__}.execute",
        ) as span:
            span.set_tag("kind", rec.kind.value)
            result = await executor.execute(
                rec=rec,
                mutations=self._mutations,
                refresh_token=credentials.refresh_token,
                customer_id=account.customer_id,
            )

        await self._rec_repo.update_status(rec_id, RecommendationStatus.EXECUTED)

        # Best-effort: capture pre-execution performance baseline from evidence
        if self._baseline_repo is not None:
            try:
                await self._capture_baseline(rec, result)
            except Exception:
                logger.warning("baseline capture failed (best-effort)", rec_id=rec_id)

        log = AuditLog.create_execute(
            recommendation_id=rec_id,
            account_id=rec.account_id,
            kind=rec.kind.value,
            payload=result,
            created_at=datetime.now(UTC),
        )
        await self._audit_log_repo.save(log)

        logger.info(
            "recommendation executed",
            rec_id=rec_id,
            kind=rec.kind.value,
            account_id=rec.account_id,
        )
        return result

    async def _capture_baseline(self, rec: Any, execution_result: dict[str, Any]) -> None:
        from adcopilot.domain.performance_tracking import PerformanceBaseline

        evidence = rec.evidence or {}
        entity_id = int(
            execution_result.get("campaign_id")
            or execution_result.get("ad_group_id")
            or evidence.get("campaign_id", 0)
            or 0
        )
        if not entity_id:
            return

        entity_type = "campaign"
        if "ad_group_id" in execution_result and "campaign_id" not in execution_result:
            entity_type = "ad_group"

        baseline = PerformanceBaseline.create(
            recommendation_id=rec.id,
            account_id=rec.account_id,
            entity_type=entity_type,  # type: ignore[arg-type]
            entity_id=entity_id,
            baseline_date=datetime.now(UTC).date(),
            cost_micros=int(evidence.get("cost_micros", 0)),
            clicks=int(evidence.get("clicks", 0)),
            impressions=int(evidence.get("impressions", 0)),
            conversions=float(evidence.get("conversions", 0.0)),
            conv_value=float(evidence.get("conv_value", 0.0)),
            captured_at=datetime.now(UTC),
        )
        await self._baseline_repo.save(baseline)
