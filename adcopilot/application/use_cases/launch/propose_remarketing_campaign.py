"""ProposeRemarketingCampaignUseCase — generate Display Remarketing campaign proposal."""

from __future__ import annotations

import uuid

import structlog

from adcopilot.domain.entities import AccountId
from adcopilot.domain.launch.entities import (
    CampaignBriefId,
    RemarketingCampaignProposal,
    RemarketingProposalId,
)
from adcopilot.domain.snapshot import RemarketingListInfo

logger = structlog.get_logger(__name__)

_MIN_LIST_MEMBERS = 1000
"""Google's minimum for RLSA / Display remarketing on Search/Display."""

_REMARKETING_BUDGET_RATIO = 0.15
"""Display remarketing gets 15 % of original Search campaign daily budget."""


class ProposeRemarketingCampaignUseCase:
    """Check remarketing list eligibility; if eligible, build a Display Remarketing proposal.

    The proposal is returned to the caller (Celery task) which sends it via
    Telegram for user approval.  No campaign is created until the user approves.

    Returns ``None`` when the account is ineligible (no lists with ≥ 1,000 members).
    """

    def __init__(self, queries_adapter) -> None:
        self._queries = queries_adapter

    async def execute(
        self,
        account_id: AccountId,
        brief_id: CampaignBriefId,
        refresh_token: str,
        customer_id: str,
        search_daily_budget_micros: int,
    ) -> RemarketingCampaignProposal | None:
        """Generate a Display Remarketing proposal if remarketing lists are eligible.

        Parameters
        ----------
        account_id
            Google Ads account identifier.
        brief_id
            The original campaign brief this remarketing campaign extends.
        refresh_token
            OAuth refresh token for this account.
        customer_id
            Google Ads customer ID (with or without dashes).
        search_daily_budget_micros
            Daily budget of the original Search campaign, used to compute the
            remarketing budget (15 %).

        Returns
        -------
        RemarketingCampaignProposal or None
            Proposal if eligible lists exist; None otherwise.
        """
        try:
            all_lists: list[RemarketingListInfo] = await self._queries.query_remarketing_lists(
                refresh_token, customer_id
            )
        except Exception as exc:
            logger.warning(
                "remarketing_proposal_lists_query_failed",
                account_id=account_id,
                error=str(exc)[:100],
            )
            return None

        eligible = [lst for lst in all_lists if lst.member_count >= _MIN_LIST_MEMBERS]
        if not eligible:
            logger.info(
                "remarketing_proposal_not_eligible",
                account_id=account_id,
                total_lists=len(all_lists),
            )
            return None

        remarketing_budget = int(search_daily_budget_micros * _REMARKETING_BUDGET_RATIO)
        user_list_ids = [lst.list_id for lst in eligible]

        proposal = RemarketingCampaignProposal(
            id=RemarketingProposalId(str(uuid.uuid4())),
            brief_id=brief_id,
            campaign_name="Remarketing | Display",
            daily_budget_micros=remarketing_budget,
            user_list_ids=user_list_ids,
        )

        logger.info(
            "remarketing_proposal_generated",
            account_id=account_id,
            proposal_id=proposal.id,
            eligible_lists=len(eligible),
            daily_budget_micros=remarketing_budget,
        )
        return proposal
