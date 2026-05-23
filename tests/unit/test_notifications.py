"""Unit tests for the notification infrastructure and use-case integration."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.domain.notification import Notification, NotificationId, NotificationType


# ---------------------------------------------------------------------------
# In-memory stub implementations
# ---------------------------------------------------------------------------


class InMemoryWebNotifier:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_digest(self, user_id, title, body, metadata=None):
        self.sent.append(
            {"type": NotificationType.DIGEST, "user_id": user_id, "title": title, "body": body, "metadata": metadata}
        )

    async def send_alert(self, user_id, title, body, metadata=None):
        self.sent.append(
            {"type": NotificationType.ALERT, "user_id": user_id, "title": title, "body": body, "metadata": metadata}
        )

    async def send_execution_result(self, user_id, title, body, metadata=None):
        self.sent.append(
            {"type": NotificationType.EXECUTION_RESULT, "user_id": user_id, "title": title, "body": body, "metadata": metadata}
        )

    async def send_reauth_required(self, user_id, title, body, metadata=None):
        self.sent.append(
            {"type": NotificationType.REAUTH_REQUIRED, "user_id": user_id, "title": title, "body": body, "metadata": metadata}
        )


class InMemoryNotificationRepository:
    def __init__(self) -> None:
        self._store: dict[str, Notification] = {}

    async def save(self, notification: Notification) -> None:
        self._store[notification.id] = notification

    async def list_for_user(self, user_id: str, limit: int = 50, offset: int = 0) -> list[Notification]:
        results = [n for n in self._store.values() if n.user_id == user_id]
        results.sort(key=lambda n: n.created_at, reverse=True)
        return results[offset : offset + limit]

    async def get(self, notification_id: str) -> Notification | None:
        return self._store.get(notification_id)

    async def mark_read(self, notification_id: str) -> None:
        n = self._store.get(notification_id)
        if n and n.read_at is None:
            self._store[notification_id] = Notification(
                id=n.id,
                user_id=n.user_id,
                notification_type=n.notification_type,
                title=n.title,
                body=n.body,
                metadata=n.metadata,
                read_at=datetime.now(UTC),
                created_at=n.created_at,
            )

    async def mark_all_read(self, user_id: str) -> None:
        now = datetime.now(UTC)
        for nid, n in list(self._store.items()):
            if n.user_id == user_id and n.read_at is None:
                self._store[nid] = Notification(
                    id=n.id,
                    user_id=n.user_id,
                    notification_type=n.notification_type,
                    title=n.title,
                    body=n.body,
                    metadata=n.metadata,
                    read_at=now,
                    created_at=n.created_at,
                )

    async def count_unread(self, user_id: str) -> int:
        return sum(1 for n in self._store.values() if n.user_id == user_id and n.read_at is None)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_notification(user_id: str = "user-1", ntype: NotificationType = NotificationType.DIGEST) -> Notification:
    return Notification(
        id=NotificationId(str(uuid.uuid4())),
        user_id=user_id,
        notification_type=ntype,
        title="Tytuł testowy",
        body="Treść testowa",
        metadata={},
        read_at=None,
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Tests: InMemoryWebNotifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_digest_records_correct_type():
    notifier = InMemoryWebNotifier()
    await notifier.send_digest("u1", "Dzienny raport rekomendacji", "Masz 3 nowe rekomendacje.", metadata={"recommendation_ids": ["r1"]})
    assert len(notifier.sent) == 1
    entry = notifier.sent[0]
    assert entry["type"] == NotificationType.DIGEST
    assert entry["user_id"] == "u1"
    assert "rekomendacje" in entry["body"] or "rekomendacji" in entry["body"]
    assert entry["metadata"]["recommendation_ids"] == ["r1"]


@pytest.mark.asyncio
async def test_send_alert_records_correct_type():
    notifier = InMemoryWebNotifier()
    await notifier.send_alert("u2", "Alert", "Coś się stało.")
    assert notifier.sent[0]["type"] == NotificationType.ALERT


# ---------------------------------------------------------------------------
# Tests: InMemoryNotificationRepository
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_read_sets_read_at():
    repo = InMemoryNotificationRepository()
    n = _make_notification()
    await repo.save(n)
    assert (await repo.get(n.id)).read_at is None
    await repo.mark_read(n.id)
    assert (await repo.get(n.id)).read_at is not None


@pytest.mark.asyncio
async def test_mark_all_read_marks_multiple():
    repo = InMemoryNotificationRepository()
    n1 = _make_notification(user_id="u1")
    n2 = _make_notification(user_id="u1")
    n3 = _make_notification(user_id="u2")
    for n in (n1, n2, n3):
        await repo.save(n)

    await repo.mark_all_read("u1")

    assert (await repo.get(n1.id)).read_at is not None
    assert (await repo.get(n2.id)).read_at is not None
    # u2 notification should be unaffected
    assert (await repo.get(n3.id)).read_at is None


@pytest.mark.asyncio
async def test_count_unread_returns_correct_number():
    repo = InMemoryNotificationRepository()
    n1 = _make_notification(user_id="u1")
    n2 = _make_notification(user_id="u1")
    for n in (n1, n2):
        await repo.save(n)

    assert await repo.count_unread("u1") == 2
    await repo.mark_read(n1.id)
    assert await repo.count_unread("u1") == 1


# ---------------------------------------------------------------------------
# Tests: SendDailyDigestUseCase calls notifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_digest_use_case_calls_notifier_when_provided():
    from datetime import date

    from adcopilot.application.use_cases.send_daily_digest import SendDailyDigestUseCase
    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.domain.recommendation import (
        Recommendation,
        RecommendationId,
        RecommendationKind,
        RecommendationSeverity,
        RecommendationStatus,
    )

    # Stub recommendation
    rec = Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=AccountId("acc-1"),
        kind=RecommendationKind.INCREASE_BUDGET,
        severity=RecommendationSeverity.HIGH,
        target={},
        payload={},
        estimated_monthly_savings_micros=1_000_000,
        evidence={},
        status=RecommendationStatus.PENDING,
        created_at=datetime.now(UTC),
    )

    # Stub repos
    account_repo = MagicMock()
    rec_repo = MagicMock()
    rec_repo.list_pending = AsyncMock(return_value=[rec])
    digest_log_repo = MagicMock()
    digest_log_repo.was_sent_today = AsyncMock(return_value=False)
    digest_log_repo.record = AsyncMock()

    notifier = InMemoryWebNotifier()

    use_case = SendDailyDigestUseCase(
        account_repo=account_repo,
        rec_repo=rec_repo,
        digest_log_repo=digest_log_repo,
        notifier=notifier,
    )

    result = await use_case.execute(
        user_id=UserId("user-123"),
        account_ids=[AccountId("acc-1")],
        today=date(2026, 5, 19),
    )

    assert result.sent is True
    assert len(notifier.sent) == 1
    assert notifier.sent[0]["type"] == NotificationType.DIGEST
    assert notifier.sent[0]["user_id"] == "user-123"


@pytest.mark.asyncio
async def test_digest_use_case_no_notifier_does_not_fail():
    from datetime import date

    from adcopilot.application.use_cases.send_daily_digest import SendDailyDigestUseCase
    from adcopilot.domain.entities import AccountId, UserId

    rec_repo = MagicMock()
    rec_repo.list_pending = AsyncMock(return_value=[])
    digest_log_repo = MagicMock()
    digest_log_repo.was_sent_today = AsyncMock(return_value=False)

    use_case = SendDailyDigestUseCase(
        account_repo=MagicMock(),
        rec_repo=rec_repo,
        digest_log_repo=digest_log_repo,
        notifier=None,
    )

    result = await use_case.execute(
        user_id=UserId("user-456"),
        account_ids=[AccountId("acc-1")],
        today=date(2026, 5, 19),
    )
    assert result.reason == "no_recommendations"
