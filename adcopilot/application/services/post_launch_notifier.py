"""Post-launch notification service.

Creates in-app notifications for campaign lifecycle events:
- CAMPAIGN_LAUNCHED: confirmation when a campaign goes live
- POST_LAUNCH_CHECKIN: periodic performance check-in (day 3, day 7, day 14, day 30)
- CONVERSION_TRACKING_REMINDER: weekly nudge when account lacks conversion tracking
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from adcopilot.domain.notification import Notification, NotificationId, NotificationType

logger = structlog.get_logger(__name__)


class PostLaunchNotifier:
    """Creates and persists post-launch notifications via the notification repository."""

    def __init__(self, notification_repo) -> None:
        self._repo = notification_repo

    async def notify_campaign_launched(
        self,
        user_id: str,
        campaign_name: str,
        account_id: str,
        proposal_id: str,
        daily_budget_pln: float,
    ) -> None:
        notification = Notification(
            id=NotificationId(str(uuid.uuid4())),
            user_id=user_id,
            notification_type=NotificationType.CAMPAIGN_LAUNCHED,
            title=f"🚀 Kampania uruchomiona: {campaign_name}",
            body=(
                f"Twoja kampania '{campaign_name}' została uruchomiona "
                f"z budżetem {daily_budget_pln:.0f} PLN/dzień. "
                f"Pierwsze dane pojawią się w ciągu 24–48 godzin."
            ),
            metadata={
                "account_id": account_id,
                "proposal_id": proposal_id,
                "daily_budget_pln": daily_budget_pln,
            },
            read_at=None,
            created_at=datetime.now(UTC),
        )
        await self._repo.save(notification)
        logger.info(
            "post_launch_notifier.campaign_launched",
            user_id=user_id,
            campaign_name=campaign_name,
        )

    async def notify_checkin(
        self,
        user_id: str,
        campaign_name: str,
        account_id: str,
        days_since_launch: int,
        clicks: int,
        impressions: int,
        cost_pln: float,
        conversions: int,
    ) -> None:
        ctr = (clicks / impressions * 100) if impressions > 0 else 0.0
        conv_rate = (conversions / clicks * 100) if clicks > 0 else 0.0

        if days_since_launch == 3:
            period = "3 dni"
        elif days_since_launch == 7:
            period = "tydzień"
        elif days_since_launch == 14:
            period = "2 tygodnie"
        else:
            period = f"{days_since_launch} dni"

        body_lines = [
            f"Mija {period} od uruchomienia kampanii '{campaign_name}'.",
            f"Kliknięcia: {clicks} | Wyświetlenia: {impressions} | CTR: {ctr:.1f}%",
            f"Wydatki: {cost_pln:.2f} PLN | Konwersje: {conversions}",
        ]
        if conv_rate > 0:
            body_lines.append(f"Współczynnik konwersji: {conv_rate:.1f}%")

        notification = Notification(
            id=NotificationId(str(uuid.uuid4())),
            user_id=user_id,
            notification_type=NotificationType.POST_LAUNCH_CHECKIN,
            title=f"📊 Check-in kampanii po {period}: {campaign_name}",
            body="\n".join(body_lines),
            metadata={
                "account_id": account_id,
                "days_since_launch": days_since_launch,
                "clicks": clicks,
                "impressions": impressions,
                "cost_pln": cost_pln,
                "conversions": conversions,
                "ctr": round(ctr, 2),
                "conv_rate": round(conv_rate, 2),
            },
            read_at=None,
            created_at=datetime.now(UTC),
        )
        await self._repo.save(notification)
        logger.info(
            "post_launch_notifier.checkin_sent",
            user_id=user_id,
            days_since_launch=days_since_launch,
            campaign_name=campaign_name,
        )

    async def notify_conversion_tracking_reminder(
        self,
        user_id: str,
        account_id: str,
        campaign_name: str,
    ) -> None:
        notification = Notification(
            id=NotificationId(str(uuid.uuid4())),
            user_id=user_id,
            notification_type=NotificationType.CONVERSION_TRACKING_REMINDER,
            title="⚠️ Brak śledzenia konwersji",
            body=(
                f"Kampania '{campaign_name}' działa bez śledzenia konwersji. "
                f"Bez niego nie możemy mierzyć zwrotu z reklamy (ROI) "
                f"ani automatycznie optymalizować stawek. "
                f"Skonfiguruj śledzenie konwersji w Ustawieniach → Śledzenie konwersji."
            ),
            metadata={
                "account_id": account_id,
                "campaign_name": campaign_name,
                "action": "setup_conversion_tracking",
            },
            read_at=None,
            created_at=datetime.now(UTC),
        )
        await self._repo.save(notification)
        logger.info(
            "post_launch_notifier.conversion_tracking_reminder",
            user_id=user_id,
            account_id=account_id,
        )
