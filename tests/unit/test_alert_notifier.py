"""Unit tests for AlertNotifier and alert callbacks."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adcopilot.domain.alert import Alert, AlertId, AlertKind, AlertSeverity, AlertStatus
from adcopilot.domain.entities import AccountId
from adcopilot.infrastructure.telegram.alert_notifier import (
    _format_alert_message,
    _format_impact,
)


def _make_alert(kind: AlertKind = AlertKind.SPEND_SPIKE, **payload_kwargs: object) -> Alert:
    return Alert(
        id=AlertId(str(uuid.uuid4())),
        account_id=AccountId(str(uuid.uuid4())),
        kind=kind,
        severity=AlertSeverity.CRITICAL,
        status=AlertStatus.OPEN,
        payload={"current_spend_micros": 5_000_000, **payload_kwargs},
        message="Spend 5.00 PLN in last hour is 3.0x the 1.67 PLN baseline.",
        created_at=datetime.now(UTC),
    )


class TestFormatImpact:
    def test_spend_spike_shows_pln(self) -> None:
        alert = _make_alert(AlertKind.SPEND_SPIKE, current_spend_micros=5_000_000)
        result = _format_impact(alert)
        assert "5" in result  # 5 PLN

    def test_no_micros_returns_dash(self) -> None:
        alert = Alert(
            id=AlertId(str(uuid.uuid4())),
            account_id=AccountId(str(uuid.uuid4())),
            kind=AlertKind.TRACKING_ERROR,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.OPEN,
            payload={"error_detail": "pixel not firing"},
            message="Tracking error.",
            created_at=datetime.now(UTC),
        )
        result = _format_impact(alert)
        assert result == "—"


class TestFormatAlertMessage:
    def test_contains_urgent_header(self) -> None:
        alert = _make_alert()
        msg = _format_alert_message(alert, "Test Account")
        assert "URGENT" in msg
        assert "Test Account" in msg
        assert alert.message in msg

    def test_contains_current_impact(self) -> None:
        alert = _make_alert(current_spend_micros=10_000_000)
        msg = _format_alert_message(alert, "My Account")
        assert "Current impact" in msg


class TestAlertNotifierSend:
    @pytest.mark.asyncio
    async def test_send_alert_calls_bot(self) -> None:
        from adcopilot.infrastructure.telegram.alert_notifier import AlertNotifier

        notifier = AlertNotifier.__new__(AlertNotifier)
        mock_bot = AsyncMock()
        notifier._bot = mock_bot

        alert = _make_alert()
        await notifier.send_alert(12345, alert, "My Account")

        mock_bot.send_message.assert_awaited_once()
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == 12345
        assert "URGENT" in call_kwargs["text"]
        assert call_kwargs["parse_mode"] == "Markdown"
        # Check keyboard has 3 buttons
        keyboard = call_kwargs["reply_markup"]
        assert len(keyboard.inline_keyboard[0]) == 3
