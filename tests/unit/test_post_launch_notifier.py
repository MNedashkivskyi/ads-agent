"""Unit tests for PostLaunchNotifier."""

from __future__ import annotations

import pytest

from adcopilot.application.services.post_launch_notifier import PostLaunchNotifier
from adcopilot.domain.notification import NotificationType


class _FakeRepo:
    def __init__(self):
        self.saved: list = []

    async def save(self, notification):
        self.saved.append(notification)


@pytest.mark.asyncio
async def test_notify_campaign_launched_saves_correct_type():
    repo = _FakeRepo()
    notifier = PostLaunchNotifier(repo)
    await notifier.notify_campaign_launched(
        user_id="u1",
        campaign_name="Hydraulik Kraków",
        account_id="acc1",
        proposal_id="p1",
        daily_budget_pln=50.0,
    )
    assert len(repo.saved) == 1
    n = repo.saved[0]
    assert n.notification_type == NotificationType.CAMPAIGN_LAUNCHED
    assert "Hydraulik Kraków" in n.title
    assert n.metadata["daily_budget_pln"] == 50.0


@pytest.mark.asyncio
async def test_notify_checkin_day3_formats_period():
    repo = _FakeRepo()
    notifier = PostLaunchNotifier(repo)
    await notifier.notify_checkin(
        user_id="u1",
        campaign_name="Elektryk Warszawa",
        account_id="acc1",
        days_since_launch=3,
        clicks=45,
        impressions=600,
        cost_pln=120.0,
        conversions=2,
    )
    n = repo.saved[0]
    assert n.notification_type == NotificationType.POST_LAUNCH_CHECKIN
    assert "3 dni" in n.title
    assert n.metadata["clicks"] == 45
    assert n.metadata["ctr"] == pytest.approx(7.5, rel=0.01)


@pytest.mark.asyncio
async def test_notify_checkin_zero_impressions_no_division_error():
    repo = _FakeRepo()
    notifier = PostLaunchNotifier(repo)
    await notifier.notify_checkin(
        user_id="u1",
        campaign_name="Test",
        account_id="acc1",
        days_since_launch=7,
        clicks=0,
        impressions=0,
        cost_pln=0.0,
        conversions=0,
    )
    n = repo.saved[0]
    assert n.metadata["ctr"] == 0.0


@pytest.mark.asyncio
async def test_notify_conversion_tracking_reminder():
    repo = _FakeRepo()
    notifier = PostLaunchNotifier(repo)
    await notifier.notify_conversion_tracking_reminder(
        user_id="u1",
        account_id="acc1",
        campaign_name="Fryzjer Poznań",
    )
    n = repo.saved[0]
    assert n.notification_type == NotificationType.CONVERSION_TRACKING_REMINDER
    assert "Fryzjer Poznań" in n.body
    assert n.metadata["action"] == "setup_conversion_tracking"
