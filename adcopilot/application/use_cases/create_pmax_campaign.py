"""CreatePMaxCampaignUseCase — generates assets via LLM and creates a PAUSED PMax campaign."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from adcopilot.application.ports.google_ads import MerchantCenterLink
from adcopilot.domain.launch.audience_signals import VERTICAL_AUDIENCES
from adcopilot.domain.launch.entities import AssetGroupProposal, PMaxCampaignProposal

logger = structlog.get_logger(__name__)

# Google Ads headline limit: 30 chars; description limit: 90 chars
_MAX_HEADLINE_LEN = 30
_MAX_DESC_LEN = 90
# PMax requires 3–15 headlines and 2–4 descriptions; we generate exactly 3 + 2.
_N_HEADLINES = 3
_N_DESCRIPTIONS = 2


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------

class LLMClientPort(Protocol):
    async def complete(self, system: str, user: str, max_tokens: int = 512) -> str: ...


class PromptVersionPort(Protocol):
    async def get_latest(self, prompt_key: str) -> Any | None: ...


class PMaxCampaignWriterPort(Protocol):
    async def create_pmax_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        proposal: PMaxCampaignProposal,
    ) -> Any: ...


# ---------------------------------------------------------------------------
# Input / Output
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CreatePMaxCampaignInput:
    customer_id: str
    refresh_token: str
    merchant_center_link: MerchantCenterLink
    monthly_budget_pln: float
    product_focus: str  # "all" or a specific product category description
    campaign_name: str
    final_url: str
    vertical: str = "ecommerce"


@dataclass(frozen=True)
class CreatePMaxCampaignResult:
    campaign_resource_name: str
    budget_resource_name: str
    asset_group_resource_names: list[str]
    proposal: PMaxCampaignProposal


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------

class CreatePMaxCampaignUseCase:
    def __init__(
        self,
        llm: LLMClientPort,
        prompt_repo: PromptVersionPort,
        pmax_writer: PMaxCampaignWriterPort,
    ) -> None:
        self._llm = llm
        self._prompt_repo = prompt_repo
        self._pmax_writer = pmax_writer

    async def execute(self, inp: CreatePMaxCampaignInput) -> CreatePMaxCampaignResult:
        # 1. Load versioned prompt (CCR-5)
        prompt_version = await self._prompt_repo.get_latest("pmax_asset_generation_v1")
        if prompt_version is None:
            raise RuntimeError("Prompt 'pmax_asset_generation_v1' not found in prompt_versions table")
        system_prompt: str = prompt_version.content

        # 2. Generate headlines + descriptions via LLM (CCR-6 — Polish output)
        user_msg = (
            f"Sklep/firma: {inp.campaign_name}\n"
            f"Fokus produktowy: {inp.product_focus}\n"
            f"URL docelowy: {inp.final_url}\n"
            f"Branża: {inp.vertical}\n"
        )
        raw = await self._llm.complete(system=system_prompt, user=user_msg, max_tokens=512)
        headlines, descriptions = _parse_assets(raw, inp.campaign_name, inp.final_url)

        # 3. Resolve audience signals for vertical
        audience_resource_names = _audience_signal_names(inp.vertical, inp.customer_id)

        # 4. Build proposal
        daily_budget_micros = int((inp.monthly_budget_pln / 30) * 1_000_000)

        asset_group = AssetGroupProposal(
            name=f"{inp.campaign_name} – Wszystkie produkty",
            headlines=headlines,
            descriptions=descriptions,
            final_url=inp.final_url,
        )

        proposal = PMaxCampaignProposal(
            id=str(uuid.uuid4()),  # type: ignore[arg-type]
            brief_id="pmax-direct",  # type: ignore[arg-type]
            campaign_name=inp.campaign_name,
            daily_budget_micros=daily_budget_micros,
            merchant_center_feed_id=inp.merchant_center_link.merchant_id,
            asset_groups=[asset_group],
            audience_signals=audience_resource_names,
        )

        # 5. Create PAUSED campaign via writer
        resources = await self._pmax_writer.create_pmax_campaign(
            customer_id=inp.customer_id,
            refresh_token=inp.refresh_token,
            proposal=proposal,
        )

        logger.info(
            "pmax.create_pmax_campaign.done",
            campaign=resources.campaign_resource_name,
            customer_id=inp.customer_id,
        )

        return CreatePMaxCampaignResult(
            campaign_resource_name=resources.campaign_resource_name,
            budget_resource_name=resources.budget_resource_name,
            asset_group_resource_names=resources.asset_group_resource_names,
            proposal=proposal,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int) -> str:
    return text[:max_len].rstrip()


def _parse_assets(raw: str, fallback_name: str, final_url: str) -> tuple[list[str], list[str]]:
    """Extract headlines and descriptions from LLM JSON response."""
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            headlines = [_truncate(h, _MAX_HEADLINE_LEN) for h in data.get("headlines", [])][:_N_HEADLINES]
            descriptions = [_truncate(d, _MAX_DESC_LEN) for d in data.get("descriptions", [])][:_N_DESCRIPTIONS]
            if len(headlines) == _N_HEADLINES and len(descriptions) == _N_DESCRIPTIONS:
                return headlines, descriptions
    except Exception:
        pass

    # Fallback to safe defaults
    domain = re.sub(r"https?://", "", final_url).split("/")[0]
    headlines = [
        _truncate(fallback_name, _MAX_HEADLINE_LEN),
        _truncate("Odkryj naszą ofertę", _MAX_HEADLINE_LEN),
        _truncate("Sprawdź promocje", _MAX_HEADLINE_LEN),
    ]
    descriptions = [
        _truncate(f"Szeroki wybór produktów w {domain}", _MAX_DESC_LEN),
        _truncate("Szybka dostawa, atrakcyjne ceny. Zamów już dziś!", _MAX_DESC_LEN),
    ]
    return headlines, descriptions


def _audience_signal_names(vertical: str, customer_id: str) -> list[str]:
    """Return Google Ads in-market audience criterion resource names for the vertical."""
    signals = VERTICAL_AUDIENCES.get(vertical.lower(), VERTICAL_AUDIENCES.get("ecommerce", []))
    return [
        f"customers/{customer_id}/userInterests/{sig.segment_id}"
        for sig in signals
    ]
