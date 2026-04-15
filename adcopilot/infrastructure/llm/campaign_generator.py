"""Campaign-proposal generation pipeline — LLM adapter.

Each of the four pipeline stages is a single LLM call that returns a
JSON object matching a Pydantic schema.  Invalid JSON is retried once
(with the parse error appended to the user prompt) before raising
``LLMError``.

Total token budget per proposal: 60 000 input + 20 000 output (tracked
approximately as character / 4).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TypeVar

import structlog
from pydantic import BaseModel, Field, field_validator

from adcopilot.application.ports.llm import LLMClient
from adcopilot.domain.exceptions import LLMError
from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CampaignBrief,
    CampaignProposal,
    CampaignProposalId,
    KeywordProposal,
    MatchType,
)

logger = structlog.get_logger(__name__)

_T = TypeVar("_T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Token-budget constants (approximate: 1 token ≈ 4 characters)
# ---------------------------------------------------------------------------

MAX_INPUT_TOKENS = 60_000
MAX_OUTPUT_TOKENS = 20_000
_CHARS_PER_TOKEN = 4

# ---------------------------------------------------------------------------
# Pydantic response schemas
# ---------------------------------------------------------------------------


class VerticalClassification(BaseModel):
    """Stage 1 output — business vertical detection."""

    vertical: str = Field(description="Top-level vertical, e.g. 'salon', 'e-commerce', 'legal'")
    sub_vertical: str | None = Field(default=None)
    competitive_level: str = Field(default="medium")
    language_hint: str | None = Field(default=None)

    @field_validator("competitive_level")
    @classmethod
    def _normalize_level(cls, v: str) -> str:
        v = v.lower().strip()
        return v if v in {"low", "medium", "high"} else "medium"


class KeywordItem(BaseModel):
    """A single keyword suggestion."""

    text: str
    match_type: str = Field(default="phrase")
    estimated_cpc_pln: float = Field(default=1.0)

    @field_validator("match_type")
    @classmethod
    def _normalize_match(cls, v: str) -> str:
        v = v.lower().strip()
        return v if v in {"broad", "phrase", "exact"} else "phrase"


class AdGroupItem(BaseModel):
    """One ad group in the campaign skeleton."""

    name: str
    theme: str = Field(description="Short theme description used in ad-copy generation")
    keywords: list[KeywordItem] = Field(min_length=3)


class CampaignStructureResponse(BaseModel):
    """Stage 2 output — campaign skeleton."""

    campaign_name: str
    bidding_strategy: str = Field(default="MAXIMIZE_CONVERSIONS")
    ad_groups: list[AdGroupItem] = Field(min_length=1, max_length=6)


class RSAVariantItem(BaseModel):
    """One RSA variant in an ad-copy response."""

    headlines: list[str] = Field(min_length=3, max_length=15)
    descriptions: list[str] = Field(min_length=2, max_length=4)
    path1: str = Field(default="")
    path2: str = Field(default="")


class AdGroupCopyResponse(BaseModel):
    """Stage 3 output — ad copy for one ad group (up to 3 RSA variants)."""

    variants: list[RSAVariantItem] = Field(min_length=1, max_length=3)


class NegativeKeywordsResponse(BaseModel):
    """Stage 4 output — campaign-level negative keywords."""

    keywords: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# JSON extraction and parsing
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]+?)\s*```", re.IGNORECASE)


def _extract_json(raw: str) -> str:
    """Strip markdown code fences, returning the bare JSON string."""
    m = _JSON_FENCE_RE.search(raw)
    return m.group(1) if m else raw.strip()


def _parse_model(raw: str, model_cls: type[_T], stage: str) -> _T:
    """Parse LLM text into *model_cls*; raises ``LLMError`` on failure."""
    json_str = _extract_json(raw)
    try:
        return model_cls.model_validate_json(json_str)
    except Exception as exc:
        snippet = json_str[:300]
        raise LLMError(
            f"Stage '{stage}' returned unparseable JSON: {exc!s}\nSnippet: {snippet}"
        ) from exc


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_VERTICAL_SYSTEM = """\
You are an expert Google Ads consultant.
Analyse the business description and classify the vertical.
Respond ONLY with a valid JSON object — no markdown, no prose:
{
  "vertical": "<string>",
  "sub_vertical": "<string or null>",
  "competitive_level": "low | medium | high",
  "language_hint": "<ISO 639-1 code or null>"
}"""

_STRUCTURE_SYSTEM = """\
You are an expert Google Ads campaign architect.
Design a complete campaign skeleton from the business brief and vertical.
Include 2-4 ad groups with 8-12 keywords each.
Respond ONLY with a valid JSON object matching this campaign skeleton schema — no markdown, no prose:
{
  "campaign_name": "<string ≤ 120 chars>",
  "bidding_strategy": "<MAXIMIZE_CONVERSIONS | TARGET_CPA | MAXIMIZE_CLICKS>",
  "ad_groups": [
    {
      "name": "<string>",
      "theme": "<short theme description>",
      "keywords": [
        { "text": "<string>", "match_type": "broad|phrase|exact", "estimated_cpc_pln": <float> }
      ]
    }
  ]
}"""

_AD_COPY_SYSTEM = """\
You are a senior Google Ads copywriter.
Write 3 responsive search ad (RSA) variants for the given ad group.
STRICT character limits — Google Ads will reject longer copy:
  • Each headline: ≤ 30 characters (count carefully!)
  • Each description: ≤ 90 characters (count carefully!)
  • path1 / path2: ≤ 15 characters each
Include at least 3 headlines and 2 descriptions per variant.
Respond ONLY with a valid JSON object — no markdown, no prose:
{
  "variants": [
    {
      "headlines": ["<≤30 chars>", "…"],
      "descriptions": ["<≤90 chars>", "…"],
      "path1": "<≤15 chars>",
      "path2": "<≤15 chars>"
    }
  ]
}
Produce exactly 3 variants in the array."""

_NEGATIVES_SYSTEM = """\
You are a Google Ads negative keyword specialist.
Return a list of campaign-level negative keywords to block irrelevant searches.
Include: standard brand-safety negatives, vertical-specific negatives, and any
user-specified exclusions.  Use plain text only (no match-type syntax).
Respond ONLY with valid JSON — no markdown, no prose:
{ "keywords": ["<string>", "…"] }"""


# ---------------------------------------------------------------------------
# User-prompt builders
# ---------------------------------------------------------------------------


def _structure_user_prompt(
    brief: CampaignBrief,
    vertical: VerticalClassification,
    feedback: str | None = None,
) -> str:
    lines = [
        f"Business description: {brief.business_description}",
        f"Location: {brief.location}",
        f"Primary action: {brief.primary_action}",
        f"Monthly budget: {brief.monthly_budget_pln} PLN",
        f"Typical customer value: {brief.typical_customer_value} PLN",
        f"Language: {brief.language}",
        f"Vertical: {vertical.vertical}",
    ]
    if vertical.sub_vertical:
        lines.append(f"Sub-vertical: {vertical.sub_vertical}")
    if brief.exclusions:
        lines.append(f"Exclusions: {', '.join(brief.exclusions)}")
    if feedback:
        lines.append(f"\nPrevious validation errors to fix:\n{feedback}")
    return "\n".join(lines)


def _ad_copy_user_prompt(
    ad_group: AdGroupItem,
    brief: CampaignBrief,
    feedback: str | None = None,
) -> str:
    kw_sample = ", ".join(kw.text for kw in ad_group.keywords[:5])
    lines = [
        f"Ad group name: {ad_group.name}",
        f"Theme: {ad_group.theme}",
        f"Sample keywords: {kw_sample}",
        f"Business: {brief.business_description}",
        f"Location: {brief.location}",
        f"Primary action: {brief.primary_action}",
        f"Language: {brief.language}",
        "REMEMBER: headline ≤ 30 chars, description ≤ 90 chars.",
    ]
    if feedback:
        lines.append(f"\nPrevious copy had these errors — fix them:\n{feedback}")
    return "\n".join(lines)


def _negatives_user_prompt(
    brief: CampaignBrief,
    vertical: VerticalClassification,
) -> str:
    lines = [
        f"Business: {brief.business_description}",
        f"Vertical: {vertical.vertical}",
    ]
    if vertical.sub_vertical:
        lines.append(f"Sub-vertical: {vertical.sub_vertical}")
    if brief.exclusions:
        lines.append(f"User exclusions: {', '.join(brief.exclusions)}")
    return "\n".join(lines)


def _extract_url(brief: CampaignBrief) -> str:
    """Return a placeholder final URL derived from the brief."""
    # In production this would come from the linked Google Ads account.
    return "https://example.com"


# ---------------------------------------------------------------------------
# CampaignGenerator
# ---------------------------------------------------------------------------


class CampaignGenerator:
    """Orchestrates the four LLM pipeline stages to produce a ``CampaignProposal``.

    Each stage calls ``_call_and_parse`` which retries once on JSON parse
    failure before raising ``LLMError``.
    """

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm
        self._input_chars_used = 0
        self._output_chars_used = 0

    # ------------------------------------------------------------------
    # Public stage methods
    # ------------------------------------------------------------------

    async def detect_vertical(
        self,
        business_description: str,
        website_url: str | None = None,
    ) -> VerticalClassification:
        """Stage 1 — classify the business vertical."""
        user = business_description
        if website_url:
            user += f"\nWebsite: {website_url}"
        return await self._call_and_parse(
            _VERTICAL_SYSTEM, user, "vertical", VerticalClassification, max_tokens=300
        )

    async def build_structure(
        self,
        brief: CampaignBrief,
        vertical: VerticalClassification,
        feedback: str | None = None,
    ) -> CampaignStructureResponse:
        """Stage 2 — design campaign skeleton."""
        user = _structure_user_prompt(brief, vertical, feedback)
        return await self._call_and_parse(
            _STRUCTURE_SYSTEM, user, "structure", CampaignStructureResponse, max_tokens=2000
        )

    async def generate_ad_copy(
        self,
        ad_group: AdGroupItem,
        brief: CampaignBrief,
        feedback: str | None = None,
    ) -> AdGroupCopyResponse:
        """Stage 3 — write RSA copy for a single ad group."""
        user = _ad_copy_user_prompt(ad_group, brief, feedback)
        return await self._call_and_parse(
            _AD_COPY_SYSTEM, user, "ad_copy", AdGroupCopyResponse, max_tokens=1200
        )

    async def generate_negatives(
        self,
        brief: CampaignBrief,
        vertical: VerticalClassification,
    ) -> NegativeKeywordsResponse:
        """Stage 4 — suggest campaign-level negative keywords."""
        user = _negatives_user_prompt(brief, vertical)
        return await self._call_and_parse(
            _NEGATIVES_SYSTEM, user, "negatives", NegativeKeywordsResponse, max_tokens=600
        )

    # ------------------------------------------------------------------
    # Domain-object assembly
    # ------------------------------------------------------------------

    def assemble_proposal(
        self,
        brief: CampaignBrief,
        structure: CampaignStructureResponse,
        ad_copies: list[AdGroupCopyResponse],
        negatives: NegativeKeywordsResponse,
    ) -> CampaignProposal:
        """Combine pipeline outputs into a ``CampaignProposal`` domain object."""
        daily_budget_micros = int(
            brief.monthly_budget_pln / Decimal("30") * Decimal("1000000")
        )

        ad_groups: list[AdGroupProposal] = []
        all_cpcs: list[int] = []

        for ag_item, copy_resp in zip(structure.ad_groups, ad_copies):
            keywords: list[KeywordProposal] = []
            for kw in ag_item.keywords:
                cpc_micros = max(1, int(kw.estimated_cpc_pln * 1_000_000))
                all_cpcs.append(cpc_micros)
                try:
                    mt = MatchType(kw.match_type.lower())
                except ValueError:
                    mt = MatchType.PHRASE
                keywords.append(
                    KeywordProposal(
                        text=kw.text,
                        match_type=mt,
                        estimated_cpc_micros=cpc_micros,
                    )
                )

            ads: list[AdProposal] = []
            for variant in copy_resp.variants:
                ads.append(
                    AdProposal(
                        headlines=variant.headlines,
                        descriptions=variant.descriptions,
                        final_url=_extract_url(brief),
                        path_segments=(variant.path1[:15], variant.path2[:15]),
                    )
                )

            ad_groups.append(
                AdGroupProposal(name=ag_item.name, keywords=keywords, ads=ads)
            )

        cpc_min = min(all_cpcs) if all_cpcs else 500_000
        cpc_max = max(all_cpcs) if all_cpcs else 2_000_000

        return CampaignProposal(
            id=CampaignProposalId(str(uuid.uuid4())),
            brief_id=brief.id,
            campaign_name=structure.campaign_name,
            daily_budget_micros=daily_budget_micros,
            location_targeting=brief.location,
            bidding_strategy=structure.bidding_strategy,
            ad_groups=ad_groups,
            negative_keywords=negatives.keywords,
            estimated_cpc_range=(cpc_min, cpc_max),
            generated_at=datetime.now(UTC),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_and_parse(
        self,
        system: str,
        user: str,
        stage: str,
        model_cls: type[_T],
        max_tokens: int = 1000,
        temperature: float = 0.3,
    ) -> _T:
        """Call LLM, parse JSON, retry ONCE on parse failure."""
        self._track_budget(system + user, stage)

        raw = await self._llm.complete(
            system=system, user=user, max_tokens=max_tokens, temperature=temperature
        )
        self._output_chars_used += len(raw)
        logger.debug("llm_response", stage=stage, chars=len(raw))

        try:
            return _parse_model(raw, model_cls, stage)
        except LLMError as first_exc:
            logger.warning(
                "llm_json_retry",
                stage=stage,
                error=str(first_exc)[:200],
            )
            retry_user = (
                user
                + f"\n\n[CORRECTION REQUIRED] Your previous response could not be "
                f"parsed as JSON. Error: {first_exc!s}\n"
                "Please respond with ONLY a valid JSON object, no markdown."
            )
            raw2 = await self._llm.complete(
                system=system,
                user=retry_user,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            self._output_chars_used += len(raw2)
            return _parse_model(raw2, model_cls, stage)  # raises LLMError if still bad

    def _track_budget(self, text: str, stage: str) -> None:
        """Warn if the cumulative input token budget is at risk."""
        self._input_chars_used += len(text)
        approx_tokens = self._input_chars_used // _CHARS_PER_TOKEN
        if approx_tokens > MAX_INPUT_TOKENS:
            logger.warning(
                "llm_budget_exceeded",
                stage=stage,
                approx_input_tokens=approx_tokens,
                limit=MAX_INPUT_TOKENS,
            )
