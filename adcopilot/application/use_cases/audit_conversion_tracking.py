"""ConversionTrackingAuditUseCase — classifies conversion actions and generates Polish diagnostics."""

from __future__ import annotations

import structlog

from adcopilot.application.ports.google_ads import GoogleAdsClientPort
from adcopilot.application.ports.llm import LLMClient
from adcopilot.application.ports.prompt_version_repository import PromptVersionRepository
from adcopilot.application.use_cases.get_latest_prompt import get_latest_prompt
from adcopilot.domain.conversion_audit import (
    ConversionActionHealth,
    ConversionActionStatus,
    ConversionAuditResult,
)
from adcopilot.domain.entities import AccountId
from adcopilot.domain.snapshot import ConversionActionSnapshot

logger = structlog.get_logger(__name__)

_PROMPT_KEY = "conversion_tracking_audit_v1"

_SYSTEM_PROMPT_FALLBACK = (
    "Jesteś ekspertem Google Ads pomagającym polskim właścicielom firm MŚP. "
    "Odpowiadaj wyłącznie po polsku. Bądź konkretny i praktyczny."
)

_GTM_GUIDE = (
    "Twoje konto nie ma skonfigurowanego żadnego śledzenia konwersji. "
    "Aby to naprawić, zainstaluj Google Tag Manager (GTM) na swojej stronie, "
    "a następnie dodaj tag konwersji Google Ads. "
    "Szczegółowy poradnik: https://support.google.com/tagmanager/answer/6103696"
)


def _classify(snapshot: ConversionActionSnapshot) -> ConversionActionHealth:
    if snapshot.status in ("REMOVED", "HIDDEN"):
        return ConversionActionHealth.DISABLED
    if snapshot.all_conversions > 0:
        return ConversionActionHealth.HEALTHY
    return ConversionActionHealth.STALE


def _overall_health(statuses: list[ConversionActionStatus]) -> ConversionActionHealth:
    if not statuses:
        return ConversionActionHealth.MISSING
    healths = {s.health for s in statuses}
    if ConversionActionHealth.HEALTHY in healths:
        return ConversionActionHealth.HEALTHY
    if ConversionActionHealth.STALE in healths:
        return ConversionActionHealth.STALE
    return ConversionActionHealth.DISABLED


def _build_action_summary(statuses: list[ConversionActionStatus]) -> str:
    lines = []
    for s in statuses:
        conv_str = f"{s.all_conversions:.1f}" if s.all_conversions else "0"
        lines.append(
            f"- {s.name}: status={s.status}, konwersje(7d)={conv_str}, ocena={s.health.value}"
        )
    return "\n".join(lines)


class ConversionTrackingAuditUseCase:
    def __init__(
        self,
        google_ads: GoogleAdsClientPort,
        llm: LLMClient,
        prompt_repo: PromptVersionRepository,
    ) -> None:
        self._google_ads = google_ads
        self._llm = llm
        self._prompt_repo = prompt_repo

    async def execute(
        self,
        refresh_token: str,
        customer_id: str,
        language: str = "pl",
    ) -> ConversionAuditResult:
        account_id = AccountId(customer_id)

        snapshots = await self._google_ads.list_conversion_actions(refresh_token, customer_id)

        if not snapshots:
            logger.info("conversion_audit.missing", account_id=customer_id)
            return ConversionAuditResult(
                account_id=account_id,
                action_statuses=[],
                diagnostic_message_pl=_GTM_GUIDE,
                overall_health=ConversionActionHealth.MISSING,
            )

        statuses = [
            ConversionActionStatus(
                action_id=s.conversion_action_id,
                name=s.name,
                status=s.status,
                all_conversions=s.all_conversions,
                health=_classify(s),
            )
            for s in snapshots
        ]

        overall = _overall_health(statuses)

        try:
            system_prompt = await get_latest_prompt(self._prompt_repo, _PROMPT_KEY)
        except KeyError:
            system_prompt = _SYSTEM_PROMPT_FALLBACK
            logger.warning("conversion_audit.prompt_missing", key=_PROMPT_KEY)

        action_summary = _build_action_summary(statuses)
        user_message = (
            f"Konto Google Ads: {customer_id}\n"
            f"Ogólna ocena śledzenia: {overall.value}\n\n"
            f"Lista akcji konwersji:\n{action_summary}\n\n"
            "Napisz diagnozę po polsku z konkretnymi instrukcjami naprawy dla każdej akcji "
            "ze statusem 'stale' lub 'disabled'. Jeśli wszystko jest zdrowe, potwierdź to krótko."
        )

        diagnostic = await self._llm.complete(
            system=system_prompt,
            user=user_message,
            max_tokens=600,
            temperature=0.2,
        )

        logger.info(
            "conversion_audit.complete",
            account_id=customer_id,
            overall=overall.value,
            action_count=len(statuses),
        )

        return ConversionAuditResult(
            account_id=account_id,
            action_statuses=statuses,
            diagnostic_message_pl=diagnostic,
            overall_health=overall,
        )
