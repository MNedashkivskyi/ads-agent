"""Unit tests for remarketing guide and verify_remarketing_tag use case."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from adcopilot.application.use_cases.launch.verify_remarketing_tag import VerifyRemarketingTagUseCase
from adcopilot.domain.snapshot import RemarketingListInfo
from adcopilot.infrastructure.telegram.remarketing_guide import get_remarketing_guide


def test_get_remarketing_guide_returns_nonempty_string():
    guide = get_remarketing_guide()
    assert isinstance(guide, str)
    assert len(guide) > 100
    assert "remarketing" in guide.lower() or "Remarketing" in guide


@pytest.mark.asyncio
async def test_no_lists_returns_not_active():
    adapter = AsyncMock()
    adapter.query_remarketing_lists.return_value = []
    uc = VerifyRemarketingTagUseCase(adapter)
    active, msg = await uc.execute("token", "123")
    assert active is False
    assert "No remarketing lists" in msg or "found" in msg


@pytest.mark.asyncio
async def test_lists_with_members_returns_active():
    adapter = AsyncMock()
    adapter.query_remarketing_lists.return_value = [
        RemarketingListInfo(list_id=1, name="All visitors", member_count=2500, status="OPEN"),
    ]
    uc = VerifyRemarketingTagUseCase(adapter)
    active, msg = await uc.execute("token", "123")
    assert active is True
    assert "2,500" in msg or "2500" in msg


@pytest.mark.asyncio
async def test_lists_with_zero_members_returns_active_but_populating():
    adapter = AsyncMock()
    adapter.query_remarketing_lists.return_value = [
        RemarketingListInfo(list_id=1, name="All visitors", member_count=0, status="OPEN"),
    ]
    uc = VerifyRemarketingTagUseCase(adapter)
    active, msg = await uc.execute("token", "123")
    assert active is True
    assert "populating" in msg.lower() or "detected" in msg.lower()


@pytest.mark.asyncio
async def test_query_failure_returns_not_active():
    adapter = AsyncMock()
    adapter.query_remarketing_lists.side_effect = Exception("API error")
    uc = VerifyRemarketingTagUseCase(adapter)
    active, msg = await uc.execute("token", "123")
    assert active is False
    assert "couldn't" in msg.lower() or "could not" in msg.lower() or "check" in msg.lower()
