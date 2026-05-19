"""UndoRecommendationUseCase: reverses an EXECUTED recommendation within the 7-day window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from adcopilot.application.ports.audit_log_repository import AuditLogRepository
from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.application.ports.repositories import (
    GoogleAdsAccountRepository,
    OAuthCredentialsRepository,
)
from adcopilot.domain.audit_log import AuditLog
from adcopilot.domain.recommendation import (
    RecommendationId,
    RecommendationKind,
    RecommendationStatus,
)

logger = structlog.get_logger(__name__)

UNDO_WINDOW_DAYS = 7


class UndoRecommendationUseCase:
    def __init__(
        self,
        rec_repo: RecommendationRepository,
        audit_log_repo: AuditLogRepository,
        account_repo: GoogleAdsAccountRepository,
        credentials_repo: OAuthCredentialsRepository,
        mutations: GoogleAdsMutationsPort,
    ) -> None:
        self._rec_repo = rec_repo
        self._audit_log_repo = audit_log_repo
        self._account_repo = account_repo
        self._credentials_repo = credentials_repo
        self._mutations = mutations

    async def execute(self, rec_id: RecommendationId) -> dict[str, Any]:
        rec = await self._rec_repo.get(rec_id)
        if rec is None:
            raise ValueError(f"Recommendation {rec_id} not found")
        if rec.status != RecommendationStatus.EXECUTED:
            raise ValueError(
                f"Recommendation {rec_id} is not EXECUTED (status={rec.status.value})"
            )

        audit_log = await self._audit_log_repo.get_latest_execute(rec_id)
        if audit_log is None:
            raise ValueError(f"No EXECUTE audit log found for recommendation {rec_id}")

        cutoff = datetime.now(UTC) - timedelta(days=UNDO_WINDOW_DAYS)
        log_ts = audit_log.created_at
        if log_ts.tzinfo is None:
            log_ts = log_ts.replace(tzinfo=UTC)
        if log_ts < cutoff:
            raise ValueError(
                f"Undo window expired: recommendation {rec_id} was executed more than "
                f"{UNDO_WINDOW_DAYS} days ago"
            )

        account = await self._account_repo.get(rec.account_id)
        if account is None:
            raise ValueError(f"Account {rec.account_id} not found")
        credentials = await self._credentials_repo.get(rec.account_id)
        if credentials is None:
            raise ValueError(f"No OAuth credentials for account {rec.account_id}")

        result = await self._undo(
            rec.kind,
            audit_log,
            rec.payload,
            credentials.refresh_token,
            account.customer_id,
        )

        await self._rec_repo.update_status(rec_id, RecommendationStatus.APPROVED)

        undo_log = AuditLog.create_execute(
            recommendation_id=rec_id,
            account_id=rec.account_id,
            kind=rec.kind.value,
            payload={**result, "undone_audit_log_id": audit_log.id},
            created_at=datetime.now(UTC),
        )
        # Override the action to UNDO
        from dataclasses import replace as dc_replace
        undo_log = dc_replace(undo_log, action="UNDO")
        await self._audit_log_repo.save(undo_log)

        logger.info("recommendation undone", rec_id=rec_id, kind=rec.kind.value)
        return result

    async def _undo(
        self,
        kind: RecommendationKind,
        audit_log: AuditLog,
        rec_payload: dict[str, Any],
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        payload = audit_log.payload

        if kind == RecommendationKind.PAUSE_KEYWORD:
            ad_group_id = int(payload["ad_group_id"])
            criterion_id = int(payload["criterion_id"])
            await self._mutations.enable_keyword(
                refresh_token=refresh_token,
                customer_id=customer_id,
                ad_group_id=ad_group_id,
                criterion_id=criterion_id,
            )
            return {"ad_group_id": ad_group_id, "criterion_id": criterion_id, "action": "enabled"}

        if kind == RecommendationKind.PAUSE_AD:
            ad_group_id = int(payload["ad_group_id"])
            ad_id = int(payload["ad_id"])
            await self._mutations.enable_ad(
                refresh_token=refresh_token,
                customer_id=customer_id,
                ad_group_id=ad_group_id,
                ad_id=ad_id,
            )
            return {"ad_group_id": ad_group_id, "ad_id": ad_id, "action": "enabled"}

        if kind == RecommendationKind.ADD_NEGATIVE_KEYWORD:
            ad_group_id = int(payload["ad_group_id"])
            keyword_text = str(payload["keyword_text"])
            match_type = str(payload.get("match_type", "EXACT"))
            await self._mutations.remove_ad_group_negative_keyword(
                refresh_token=refresh_token,
                customer_id=customer_id,
                ad_group_id=ad_group_id,
                keyword_text=keyword_text,
                match_type=match_type,
            )
            return {
                "ad_group_id": ad_group_id,
                "keyword_text": keyword_text,
                "action": "negative_removed",
            }

        if kind == RecommendationKind.INCREASE_BUDGET:
            campaign_id = int(payload["campaign_id"])
            old_budget = int(rec_payload.get("current_budget_micros", 0))
            await self._mutations.update_campaign_budget(
                refresh_token=refresh_token,
                customer_id=customer_id,
                campaign_id=campaign_id,
                new_budget_micros=old_budget,
            )
            return {
                "campaign_id": campaign_id,
                "restored_budget_micros": old_budget,
                "action": "budget_restored",
            }

        if kind == RecommendationKind.CHANGE_MATCH_TYPE:
            ad_group_id = int(payload["ad_group_id"])
            criterion_id = int(payload["criterion_id"])
            old_match_type = str(payload.get("old_match_type", "BROAD"))
            await self._mutations.change_keyword_match_type(
                refresh_token=refresh_token,
                customer_id=customer_id,
                ad_group_id=ad_group_id,
                criterion_id=criterion_id,
                match_type=old_match_type,
            )
            return {
                "ad_group_id": ad_group_id,
                "criterion_id": criterion_id,
                "restored_match_type": old_match_type,
                "action": "match_type_restored",
            }

        if kind == RecommendationKind.ADJUST_BIDDING_STRATEGY:
            campaign_id = int(payload["campaign_id"])
            old_strategy = str(payload.get("old_strategy", rec_payload.get("current_strategy", "")))
            await self._mutations.set_campaign_bidding_strategy(
                refresh_token=refresh_token,
                customer_id=customer_id,
                campaign_id=campaign_id,
                bidding_strategy=old_strategy,
            )
            return {
                "campaign_id": campaign_id,
                "restored_strategy": old_strategy,
                "action": "bidding_strategy_restored",
            }

        if kind == RecommendationKind.ADJUST_BUDGET:
            campaign_id = int(payload["campaign_id"])
            old_budget = int(rec_payload.get("current_budget_micros", 0))
            await self._mutations.update_campaign_budget(
                refresh_token=refresh_token,
                customer_id=customer_id,
                campaign_id=campaign_id,
                new_budget_micros=old_budget,
            )
            return {
                "campaign_id": campaign_id,
                "restored_budget_micros": old_budget,
                "action": "budget_restored",
            }

        if kind in (
            RecommendationKind.ADD_SITELINKS,
            RecommendationKind.ADD_CALLOUTS,
            RecommendationKind.ADD_STRUCTURED_SNIPPETS,
        ):
            ca_rns: list[str] = list(payload.get("campaign_asset_resource_names", []))
            if ca_rns:
                await self._mutations.remove_campaign_assets(
                    refresh_token=refresh_token,
                    customer_id=customer_id,
                    campaign_asset_resource_names=ca_rns,
                )
            return {"campaign_asset_resource_names": ca_rns, "action": "extensions_removed"}

        if kind == RecommendationKind.MATCH_TYPE_REDUNDANCY:
            ad_group_id = int(payload["ad_group_id"])
            criterion_id = int(payload["criterion_id"])
            await self._mutations.enable_keyword(
                refresh_token=refresh_token,
                customer_id=customer_id,
                ad_group_id=ad_group_id,
                criterion_id=criterion_id,
            )
            return {"ad_group_id": ad_group_id, "criterion_id": criterion_id, "action": "broad_keyword_enabled"}

        if kind == RecommendationKind.NEGATIVE_KEYWORD_CONFLICT:
            campaign_id = int(payload["campaign_id"])
            keyword_text = str(payload["keyword_text"])
            match_type = str(payload.get("match_type", "EXACT"))
            conflict_scope = str(payload.get("conflict_scope", "campaign"))
            ad_group_id = payload.get("ad_group_id")
            if conflict_scope == "ad_group" and ad_group_id:
                await self._mutations.add_ad_group_negative_keyword(
                    refresh_token=refresh_token,
                    customer_id=customer_id,
                    ad_group_id=int(ad_group_id),
                    keyword_text=keyword_text,
                    match_type=match_type,
                )
            else:
                await self._mutations.add_campaign_negative_keyword(
                    refresh_token=refresh_token,
                    customer_id=customer_id,
                    campaign_id=campaign_id,
                    keyword_text=keyword_text,
                    match_type=match_type,
                )
            return {"campaign_id": campaign_id, "keyword_text": keyword_text, "action": "negative_keyword_restored"}

        if kind == RecommendationKind.RELAX_TARGET_CPA:
            campaign_id = int(payload["campaign_id"])
            original_cpa = int(payload["original_target_cpa_micros"])
            await self._mutations.set_target_cpa(
                refresh_token=refresh_token,
                customer_id=customer_id,
                campaign_id=campaign_id,
                target_cpa_micros=original_cpa,
            )
            return {"campaign_id": campaign_id, "restored_target_cpa_micros": original_cpa, "action": "target_cpa_restored"}

        if kind == RecommendationKind.REALLOCATE_BUDGET:
            from_campaign_id = int(payload["from_campaign_id"])
            to_campaign_id = int(payload["to_campaign_id"])
            old_donor = int(payload["old_donor_budget_micros"])
            old_receiver = int(payload["old_receiver_budget_micros"])
            await self._mutations.update_campaign_budget(
                refresh_token=refresh_token,
                customer_id=customer_id,
                campaign_id=from_campaign_id,
                new_budget_micros=old_donor,
            )
            await self._mutations.update_campaign_budget(
                refresh_token=refresh_token,
                customer_id=customer_id,
                campaign_id=to_campaign_id,
                new_budget_micros=old_receiver,
            )
            return {
                "from_campaign_id": from_campaign_id,
                "to_campaign_id": to_campaign_id,
                "restored_donor_budget_micros": old_donor,
                "restored_receiver_budget_micros": old_receiver,
                "action": "budget_reallocation_undone",
            }

        if kind == RecommendationKind.AD_SCHEDULE_ADJUSTMENT:
            campaign_id = int(payload["campaign_id"])
            hour_of_day = int(payload["hour_of_day"])
            await self._mutations.remove_ad_schedule_criterion(
                refresh_token=refresh_token,
                customer_id=customer_id,
                campaign_id=campaign_id,
                hour_of_day=hour_of_day,
            )
            return {"campaign_id": campaign_id, "hour_of_day": hour_of_day, "action": "ad_schedule_removed"}

        if kind == RecommendationKind.GEO_EXCLUSION:
            campaign_id = int(payload["campaign_id"])
            location_id = int(payload["location_id"])
            await self._mutations.remove_geo_exclusion(
                refresh_token=refresh_token,
                customer_id=customer_id,
                campaign_id=campaign_id,
                location_id=location_id,
            )
            return {"campaign_id": campaign_id, "location_id": location_id, "action": "geo_exclusion_removed"}

        if kind == RecommendationKind.DEVICE_BID_ADJUSTMENT:
            campaign_id = int(payload["campaign_id"])
            await self._mutations.remove_device_bid_modifier(
                refresh_token=refresh_token,
                customer_id=customer_id,
                campaign_id=campaign_id,
            )
            return {"campaign_id": campaign_id, "action": "device_bid_modifier_removed"}

        if kind == RecommendationKind.PROMOTE_SEARCH_TERM:
            ad_group_id = int(payload["suggested_ad_group_id"])
            search_term: str = payload["search_term"]
            match_type: str = payload.get("suggested_match_type", "EXACT")
            await self._mutations.pause_ad_group_keyword_by_text(
                refresh_token=refresh_token,
                customer_id=customer_id,
                ad_group_id=ad_group_id,
                keyword_text=search_term,
                match_type=match_type,
            )
            return {
                "ad_group_id": ad_group_id,
                "search_term": search_term,
                "action": "promoted_keyword_paused",
            }

        if kind in (RecommendationKind.AD_FATIGUE, RecommendationKind.WEAK_RSA_STRENGTH):
            ad_group_id = int(payload["ad_group_id"])
            created_ad_ids: list[int] = payload.get("created_ad_ids", [])
            paused_ad_id: int | None = payload.get("paused_ad_id")
            for ad_id in created_ad_ids:
                await self._mutations.pause_ad(
                    refresh_token=refresh_token,
                    customer_id=customer_id,
                    ad_group_id=ad_group_id,
                    ad_id=ad_id,
                )
            if paused_ad_id:
                await self._mutations.enable_ad(
                    refresh_token=refresh_token,
                    customer_id=customer_id,
                    ad_group_id=ad_group_id,
                    ad_id=paused_ad_id,
                )
            return {
                "ad_group_id": ad_group_id,
                "paused_new_ad_ids": created_ad_ids,
                "re_enabled_ad_id": paused_ad_id,
                "action": "ad_copy_refresh_undone",
            }

        raise ValueError(f"No undo logic for {kind.value}")
