"""VerifyConversionFiringUseCase — confirm a conversion action records events.

After a user installs the tag from :mod:`setup_conversion_tracking`, this checks
whether the conversion action is ENABLED and has recorded conversions in the
recent window. It never raises — it returns a status the caller surfaces to the
user (web notification / API response).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import structlog

from adcopilot.domain.snapshot import ConversionActionSnapshot

logger = structlog.get_logger(__name__)


class _ConversionActionReader(Protocol):
    async def list_conversion_actions(
        self, refresh_token: str, customer_id: str
    ) -> list[ConversionActionSnapshot]: ...


@dataclass(frozen=True)
class ConversionFiringStatus:
    conversion_action_id: int
    found: bool
    enabled: bool
    recent_conversions: float
    is_firing: bool
    message_pl: str


class VerifyConversionFiringUseCase:
    def __init__(self, reader: _ConversionActionReader) -> None:
        self._reader = reader

    async def execute(
        self,
        *,
        refresh_token: str,
        customer_id: str,
        conversion_action_id: int,
    ) -> ConversionFiringStatus:
        try:
            actions = await self._reader.list_conversion_actions(
                refresh_token, customer_id
            )
        except Exception as exc:  # never raise — report as "unverified"
            logger.warning(
                "verify conversion firing failed to read actions",
                customer_id=customer_id,
                error=str(exc),
            )
            return ConversionFiringStatus(
                conversion_action_id=conversion_action_id,
                found=False,
                enabled=False,
                recent_conversions=0.0,
                is_firing=False,
                message_pl=(
                    "Nie udało się sprawdzić statusu konwersji. "
                    "Spróbuj ponownie za chwilę."
                ),
            )

        match = next(
            (a for a in actions if a.conversion_action_id == conversion_action_id),
            None,
        )
        if match is None:
            return ConversionFiringStatus(
                conversion_action_id=conversion_action_id,
                found=False,
                enabled=False,
                recent_conversions=0.0,
                is_firing=False,
                message_pl=(
                    "Nie znaleziono tej akcji konwersji na koncie. "
                    "Upewnij się, że została utworzona poprawnie."
                ),
            )

        enabled = match.status == "ENABLED"
        recent = match.all_conversions
        is_firing = enabled and recent > 0

        if is_firing:
            message = (
                f"Śledzenie działa — zarejestrowano {recent:g} konwersji "
                "w ostatnich 7 dniach."
            )
        elif enabled:
            message = (
                "Akcja konwersji jest aktywna, ale nie zarejestrowano jeszcze "
                "żadnych konwersji. Wykonaj testową konwersję na stronie i "
                "odczekaj kilka godzin."
            )
        else:
            message = (
                "Akcja konwersji nie jest aktywna (status: "
                f"{match.status}). Sprawdź konfigurację w Google Ads."
            )

        return ConversionFiringStatus(
            conversion_action_id=conversion_action_id,
            found=True,
            enabled=enabled,
            recent_conversions=recent,
            is_firing=is_firing,
            message_pl=message,
        )
