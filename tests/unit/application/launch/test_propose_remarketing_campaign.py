"""Unit tests for ProposeRemarketingCampaignUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from adcopilot.application.use_cases.launch.propose_remarketing_campaign import (
    ProposeRemarketingCampaignUseCase,
)
from adcopilot.domain.launch.entities import RemarketingCampaignProposal
from adcopilot.domain.snapshot import RemarketingListInfo

_ACCOUNT_ID = "acc-1"
_BRIEF_ID = "brief-1"
_REFRESH_TOKEN = "token"
_CUSTOMER_ID = "123"
_SEARCH_BUDGET = 10_000_000  # 10 PLN/day in micros


def _make_list(list_id: int, members: int) -> RemarketingListInfo:
    return RemarketingListInfo(
        list_id=list_id, name=f"List {list_id}", member_count=members, status="OPEN"
    )


def _make_uc(lists):
    queries = AsyncMock()
    queries.query_remarketing_lists.return_value = lists
    return ProposeRemarketingCampaignUseCase(queries), queries


@pytest.mark.asyncio
async def test_no_lists_returns_none():
    uc, _ = _make_uc([])
    result = await uc.execute(_ACCOUNT_ID, _BRIEF_ID, _REFRESH_TOKEN, _CUSTOMER_ID, _SEARCH_BUDGET)
    assert result is None


@pytest.mark.asyncio
async def test_list_below_threshold_returns_none():
    uc, _ = _make_uc([_make_list(1, 999)])
    result = await uc.execute(_ACCOUNT_ID, _BRIEF_ID, _REFRESH_TOKEN, _CUSTOMER_ID, _SEARCH_BUDGET)
    assert result is None


@pytest.mark.asyncio
async def test_eligible_list_returns_proposal():
    uc, _ = _make_uc([_make_list(1, 2000)])
    result = await uc.execute(_ACCOUNT_ID, _BRIEF_ID, _REFRESH_TOKEN, _CUSTOMER_ID, _SEARCH_BUDGET)
    assert result is not None
    assert isinstance(result, RemarketingCampaignProposal)
    assert result.brief_id == _BRIEF_ID
    assert result.user_list_ids == [1]


@pytest.mark.asyncio
async def test_budget_is_15_percent_of_search():
    uc, _ = _make_uc([_make_list(1, 5000)])
    result = await uc.execute(_ACCOUNT_ID, _BRIEF_ID, _REFRESH_TOKEN, _CUSTOMER_ID, _SEARCH_BUDGET)
    assert result is not None
    expected = int(_SEARCH_BUDGET * 0.15)
    assert result.daily_budget_micros == expected


@pytest.mark.asyncio
async def test_multiple_eligible_lists_all_included():
    uc, _ = _make_uc([_make_list(1, 1500), _make_list(2, 3000), _make_list(3, 800)])
    result = await uc.execute(_ACCOUNT_ID, _BRIEF_ID, _REFRESH_TOKEN, _CUSTOMER_ID, _SEARCH_BUDGET)
    assert result is not None
    assert 1 in result.user_list_ids
    assert 2 in result.user_list_ids
    assert 3 not in result.user_list_ids  # below threshold


@pytest.mark.asyncio
async def test_query_failure_returns_none():
    queries = AsyncMock()
    queries.query_remarketing_lists.side_effect = Exception("API error")
    uc = ProposeRemarketingCampaignUseCase(queries)
    result = await uc.execute(_ACCOUNT_ID, _BRIEF_ID, _REFRESH_TOKEN, _CUSTOMER_ID, _SEARCH_BUDGET)
    assert result is None


@pytest.mark.asyncio
async def test_proposal_uses_maximize_conversions():
    uc, _ = _make_uc([_make_list(1, 2000)])
    result = await uc.execute(_ACCOUNT_ID, _BRIEF_ID, _REFRESH_TOKEN, _CUSTOMER_ID, _SEARCH_BUDGET)
    assert result is not None
    assert result.bidding_strategy == "MAXIMIZE_CONVERSIONS"
