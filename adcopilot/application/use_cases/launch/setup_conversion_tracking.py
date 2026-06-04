"""SetupConversionTrackingUseCase — bootstrap a macro conversion action.

Creates a webpage conversion action (if the account has none), reads back its
installable tag, and pairs it with the right platform installation guide,
pre-filled with the account's real ``AW-<id>/<label>``. No-ops when the account
already has macro tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import structlog

from adcopilot.application.use_cases.launch.check_conversion_setup import (
    has_macro_conversion_tracking,
)
from adcopilot.domain.conversion_tracking.installation_guides import (
    InstallationGuide,
    get_guide,
)
from adcopilot.domain.conversion_tracking.setup import (
    ConversionActionTag,
    validate_macro_category,
)
from adcopilot.domain.snapshot import ConversionActionSnapshot

logger = structlog.get_logger(__name__)

# Polish default names for each macro category.
_DEFAULT_NAMES_PL: dict[str, str] = {
    "PURCHASE": "Zakup",
    "LEAD": "Kontakt / Zapytanie",
    "SIGNUP": "Rejestracja",
    "PHONE_CALL": "Telefon",
}


class _ConversionActionReader(Protocol):
    async def list_conversion_actions(
        self, refresh_token: str, customer_id: str
    ) -> list[ConversionActionSnapshot]: ...


class _ConversionActionWriter(Protocol):
    async def create_conversion_action(
        self,
        refresh_token: str,
        customer_id: str,
        *,
        name: str,
        category: str,
        value_micros: int | None = ...,
        counting_type: str = ...,
        default_currency: str = ...,
    ) -> int: ...

    async def get_conversion_action_tag_snippets(
        self, refresh_token: str, customer_id: str, conversion_action_id: int
    ) -> ConversionActionTag: ...


@dataclass(frozen=True)
class ConversionTrackingSetupResult:
    """Outcome of a setup attempt.

    ``already_configured`` is True when the account already had a macro action
    (nothing was created). Otherwise ``conversion_action_id``, ``tag`` and
    ``guide`` describe the freshly-created action ready to install.
    """

    already_configured: bool
    conversion_action_id: int | None
    tag: ConversionActionTag | None
    guide: InstallationGuide | None
    message_pl: str


class SetupConversionTrackingUseCase:
    def __init__(
        self,
        reader: _ConversionActionReader,
        writer: _ConversionActionWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer

    async def execute(
        self,
        *,
        refresh_token: str,
        customer_id: str,
        category: str,
        platform: str = "custom",
        value_micros: int | None = None,
        name: str | None = None,
        default_currency: str = "PLN",
    ) -> ConversionTrackingSetupResult:
        category = validate_macro_category(category)

        existing = await self._reader.list_conversion_actions(refresh_token, customer_id)
        if has_macro_conversion_tracking(existing):
            logger.info(
                "conversion tracking already configured",
                customer_id=customer_id,
            )
            return ConversionTrackingSetupResult(
                already_configured=True,
                conversion_action_id=None,
                tag=None,
                guide=None,
                message_pl=(
                    "To konto ma już skonfigurowane śledzenie konwersji — "
                    "nie utworzono nowej akcji."
                ),
            )

        action_name = name or _DEFAULT_NAMES_PL[category]
        conversion_action_id = await self._writer.create_conversion_action(
            refresh_token,
            customer_id,
            name=action_name,
            category=category,
            value_micros=value_micros,
            default_currency=default_currency,
        )
        tag = await self._writer.get_conversion_action_tag_snippets(
            refresh_token, customer_id, conversion_action_id
        )
        guide = get_guide(platform)

        logger.info(
            "conversion tracking bootstrapped",
            customer_id=customer_id,
            conversion_action_id=conversion_action_id,
            category=category,
            platform=platform,
        )
        return ConversionTrackingSetupResult(
            already_configured=False,
            conversion_action_id=conversion_action_id,
            tag=tag,
            guide=guide,
            message_pl=(
                f"Utworzono akcję konwersji „{action_name}”. "
                "Zainstaluj tag zgodnie z instrukcją, a następnie zweryfikuj, "
                "czy konwersje są rejestrowane."
            ),
        )
