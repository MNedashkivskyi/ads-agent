"""Unit tests for AlertKindSuppression — 24h suppression of acknowledged alert kinds."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from adcopilot.application.anomaly.anomaly_detection_use_case import AnomalyDetectionUseCase
from adcopilot.domain.alert import AlertKind
from adcopilot.domain.entities import AccountId


class TestKindSuppressionInUseCase:
    """Verify that suppressed kinds are skipped even under quota."""

    @pytest.mark.asyncio
    async def test_suppressed_kind_is_skipped(self) -> None:
        account_id = AccountId(str(uuid.uuid4()))

        mock_metrics = AsyncMock()
        # Spend spike would normally trigger
        mock_metrics.get_last_n_hours.return_value = [
            type("H", (), {"spend_micros": 10_000_000, "hour": 10, "conversions": 0, "date": "2024-01-01"})()
        ]
        mock_metrics.get_baseline_for_hour.return_value = type(
            "B", (), {"spend_micros": 1_000_000, "conversions": 1}
        )()
        mock_metrics.get_last_n_hours.return_value = [
            type("H", (), {"spend_micros": 10_000_000, "hour": 10, "conversions": 1, "date": "2024-01-01"})()
        ]
        mock_metrics.get_daily_budget_status.return_value = []
        mock_metrics.get_conversion_tracking_status.return_value = type(
            "S", (), {"has_errors": False, "error_detail": None}
        )()
        mock_metrics.get_impression_share_wow.return_value = None

        mock_alert_repo = AsyncMock()
        mock_alert_repo.count_since.return_value = 0
        mock_alert_repo.is_kind_suppressed.return_value = True  # All kinds suppressed

        uc = AnomalyDetectionUseCase(metrics=mock_metrics, alert_repo=mock_alert_repo)
        result = await uc.execute(
            account_id,
            "123-456-7890",
            "fake_refresh_token",
            now=datetime.now(UTC),
        )

        assert result.alerts_created == 0
        mock_alert_repo.save.assert_not_called()
