"""AddRlsaAudiencesUseCase — add RLSA observation audiences to Search campaigns."""

from __future__ import annotations

import structlog

from adcopilot.domain.entities import AccountId
from adcopilot.domain.snapshot import RemarketingListInfo

logger = structlog.get_logger(__name__)

_MIN_LIST_MEMBERS = 1000
"""Google's minimum size for RLSA on Search campaigns."""


class AddRlsaAudiencesUseCase:
    """For accounts with eligible remarketing lists, add RLSA observation audiences.

    Observation mode does not restrict targeting — it layers user-list signals
    so Smart Bidding can identify and bid higher on returning visitors who are
    more likely to convert.

    Only acts on lists with ≥ 1,000 members (Google's RLSA minimum for Search).
    """

    def __init__(self, queries_adapter, campaign_writer) -> None:
        self._queries = queries_adapter
        self._writer = campaign_writer

    async def execute(
        self,
        account_id: AccountId,
        refresh_token: str,
        customer_id: str,
    ) -> int:
        """Add RLSA audiences to all ad groups in Search campaigns.

        Returns the number of ad group criteria created.
        """
        # 1. Fetch remarketing lists
        try:
            all_lists: list[RemarketingListInfo] = await self._queries.query_remarketing_lists(
                refresh_token, customer_id
            )
        except Exception as exc:
            logger.warning(
                "rlsa_query_remarketing_lists_failed",
                account_id=account_id,
                error=str(exc)[:100],
            )
            return 0

        eligible = [lst for lst in all_lists if lst.member_count >= _MIN_LIST_MEMBERS]
        if not eligible:
            logger.info(
                "rlsa_no_eligible_lists",
                account_id=account_id,
                total_lists=len(all_lists),
            )
            return 0

        # 2. Fetch ad groups for this account (Search campaigns only)
        try:
            ad_group_rns = await self._writer.get_search_ad_group_resource_names(
                customer_id, refresh_token
            )
        except Exception as exc:
            logger.warning(
                "rlsa_get_ad_groups_failed",
                account_id=account_id,
                error=str(exc)[:100],
            )
            return 0

        if not ad_group_rns:
            return 0

        # 3. Add RLSA user-list audiences in observation mode
        total_added = 0
        for lst in eligible:
            try:
                rns = await self._writer.create_rlsa_audiences(
                    customer_id=customer_id,
                    refresh_token=refresh_token,
                    ad_group_resource_names=ad_group_rns,
                    user_list_id=lst.list_id,
                    user_list_name=lst.name,
                )
                total_added += len(rns)
                logger.info(
                    "rlsa_audiences_added",
                    account_id=account_id,
                    list_id=lst.list_id,
                    list_name=lst.name,
                    criteria_created=len(rns),
                )
            except Exception as exc:
                logger.warning(
                    "rlsa_add_list_failed",
                    account_id=account_id,
                    list_id=lst.list_id,
                    error=str(exc)[:100],
                )

        return total_added
