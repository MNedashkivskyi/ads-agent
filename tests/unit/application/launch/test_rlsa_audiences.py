"""Unit tests for AddRlsaAudiencesUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from adcopilot.application.use_cases.add_rlsa_audiences import AddRlsaAudiencesUseCase
from adcopilot.domain.snapshot import RemarketingListInfo

_ACCOUNT_ID = "acc-1"
_REFRESH_TOKEN = "token"
_CUSTOMER_ID = "123"
_AG_RNS = ["customers/123/adGroups/1", "customers/123/adGroups/2"]


def _make_list(list_id: int, members: int) -> RemarketingListInfo:
    return RemarketingListInfo(
        list_id=list_id,
        name=f"List {list_id}",
        member_count=members,
        status="OPEN",
    )


def _make_uc(lists, ag_rns=_AG_RNS, create_rns=None):
    queries = AsyncMock()
    queries.query_remarketing_lists.return_value = lists
    writer = AsyncMock()
    writer.get_search_ad_group_resource_names.return_value = ag_rns
    writer.create_rlsa_audiences.return_value = create_rns or [f"crit/{i}" for i in range(len(ag_rns))]
    return AddRlsaAudiencesUseCase(queries, writer), queries, writer


@pytest.mark.asyncio
async def test_no_lists_returns_zero():
    uc, queries, writer = _make_uc(lists=[])
    result = await uc.execute(_ACCOUNT_ID, _REFRESH_TOKEN, _CUSTOMER_ID)
    assert result == 0
    writer.create_rlsa_audiences.assert_not_called()


@pytest.mark.asyncio
async def test_list_below_threshold_skipped():
    uc, queries, writer = _make_uc(lists=[_make_list(1, 999)])
    result = await uc.execute(_ACCOUNT_ID, _REFRESH_TOKEN, _CUSTOMER_ID)
    assert result == 0
    writer.create_rlsa_audiences.assert_not_called()


@pytest.mark.asyncio
async def test_eligible_list_adds_audiences():
    uc, queries, writer = _make_uc(
        lists=[_make_list(1, 1500)],
        ag_rns=_AG_RNS,
        create_rns=["crit/1", "crit/2"],
    )
    result = await uc.execute(_ACCOUNT_ID, _REFRESH_TOKEN, _CUSTOMER_ID)
    assert result == 2
    writer.create_rlsa_audiences.assert_called_once_with(
        customer_id=_CUSTOMER_ID,
        refresh_token=_REFRESH_TOKEN,
        ad_group_resource_names=_AG_RNS,
        user_list_id=1,
        user_list_name="List 1",
    )


@pytest.mark.asyncio
async def test_multiple_eligible_lists_all_added():
    uc, queries, writer = _make_uc(
        lists=[_make_list(1, 2000), _make_list(2, 5000)],
        ag_rns=_AG_RNS,
        create_rns=["crit/1", "crit/2"],
    )
    result = await uc.execute(_ACCOUNT_ID, _REFRESH_TOKEN, _CUSTOMER_ID)
    assert result == 4  # 2 criteria per list × 2 lists
    assert writer.create_rlsa_audiences.call_count == 2


@pytest.mark.asyncio
async def test_no_ad_groups_returns_zero():
    uc, queries, writer = _make_uc(lists=[_make_list(1, 2000)], ag_rns=[])
    result = await uc.execute(_ACCOUNT_ID, _REFRESH_TOKEN, _CUSTOMER_ID)
    assert result == 0
    writer.create_rlsa_audiences.assert_not_called()


@pytest.mark.asyncio
async def test_query_failure_returns_zero():
    queries = AsyncMock()
    queries.query_remarketing_lists.side_effect = Exception("API error")
    writer = AsyncMock()
    uc = AddRlsaAudiencesUseCase(queries, writer)
    result = await uc.execute(_ACCOUNT_ID, _REFRESH_TOKEN, _CUSTOMER_ID)
    assert result == 0
    writer.create_rlsa_audiences.assert_not_called()
