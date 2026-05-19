"""Validate that conversion tracking is receiving data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import structlog

from adcopilot.application.ports.google_ads import GoogleAdsClientPort

logger = structlog.get_logger(__name__)

ValidationStatus = Literal["passing", "failing", "no_data_yet"]

_GRACE_PERIOD_HOURS = 48


@dataclass
class ConversionValidationResult:
    status: ValidationStatus
    message_pl: str
    failing_actions: list[dict] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.failing_actions is None:
            self.failing_actions = []


class ValidateConversionTrackingUseCase:
    def __init__(self, google_ads: GoogleAdsClientPort) -> None:
        self._google_ads = google_ads

    async def execute(
        self,
        refresh_token: str,
        customer_id: str,
    ) -> ConversionValidationResult:
        snapshots = await self._google_ads.list_conversion_actions(refresh_token, customer_id)

        if not snapshots:
            return ConversionValidationResult(
                status="failing",
                message_pl=(
                    "Nie znaleziono żadnych akcji konwersji w tym koncie Google Ads. "
                    "Skonfiguruj śledzenie konwersji korzystając z poradnika instalacji."
                ),
            )

        enabled = [s for s in snapshots if s.status == "ENABLED"]

        if not enabled:
            return ConversionValidationResult(
                status="failing",
                message_pl=(
                    "Wszystkie akcje konwersji są wyłączone lub usunięte. "
                    "Włącz przynajmniej jedną akcję konwersji w Google Ads."
                ),
            )

        passing = [s for s in enabled if s.all_conversions > 0]

        if passing:
            return ConversionValidationResult(
                status="passing",
                message_pl=(
                    f"Śledzenie konwersji działa poprawnie. "
                    f"{len(passing)} z {len(enabled)} aktywnych akcji rejestruje konwersje."
                ),
            )

        failing_details = [
            {
                "name": s.name,
                "status": s.status,
                "all_conversions": s.all_conversions,
            }
            for s in enabled
        ]

        return ConversionValidationResult(
            status="no_data_yet",
            message_pl=(
                "Akcje konwersji są skonfigurowane, ale nie zarejestrowano jeszcze żadnych konwersji. "
                "Jeśli instalacja jest świeża, poczekaj 24-48 godzin. "
                "Upewnij się, że tag GTM jest aktywny używając Google Tag Assistant."
            ),
            failing_actions=failing_details,
        )
