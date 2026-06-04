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
from typing import Annotated, TypeVar

import structlog
from pydantic import BaseModel, BeforeValidator, Field, field_validator

from adcopilot.application.ports.llm import LLMClient
from adcopilot.domain.exceptions import LLMError
from adcopilot.domain.launch.bidding_resolver import resolve_bidding_strategy
from adcopilot.domain.launch.budget_tier import classify_budget_tier
from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CalloutProposal,
    CampaignBrief,
    CampaignProposal,
    CampaignProposalId,
    KeywordProposal,
    MatchType,
    SitelinkProposal,
    StructuredSnippetProposal,
)
from adcopilot.domain.launch.structure_rules import build_structure_prompt_fragment

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
    """A single keyword suggestion.

    ``avg_monthly_searches`` and ``competition`` are populated from real Keyword
    Planner data when a planner is available; ``None`` when no demand data was
    attached (LLM/template-only keyword).
    """

    text: str
    match_type: str = Field(default="phrase")
    estimated_cpc_pln: float = Field(default=1.0)
    avg_monthly_searches: int | None = Field(default=None)
    competition: str | None = Field(default=None)

    @field_validator("match_type")
    @classmethod
    def _normalize_match(cls, v: str) -> str:
        v = v.lower().strip()
        return v if v in {"broad", "phrase", "exact"} else "phrase"


_INTENT_TIERS = {"HIGH_INTENT", "MID_INTENT", "DISCOVERY"}


class AdGroupItem(BaseModel):
    """One ad group in the campaign skeleton."""

    name: str
    theme: str = Field(description="Short theme description used in ad-copy generation")
    keywords: list[KeywordItem] = Field(min_length=3)
    intent_tier: str | None = Field(
        default=None, description="HIGH_INTENT | MID_INTENT | DISCOVERY"
    )
    is_brand: bool = Field(default=False)

    @field_validator("intent_tier")
    @classmethod
    def _normalize_intent(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.upper().strip().replace("-", "_").replace(" ", "_")
        return v if v in _INTENT_TIERS else None


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


class BrandKeywordItem(BaseModel):
    """A single brand keyword (exact match)."""

    text: str
    estimated_cpc_pln: float = Field(default=0.5)


class BrandAdItem(BaseModel):
    """Brand RSA — simple, name-focused copy."""

    headlines: list[str] = Field(min_length=3, max_length=15)
    descriptions: list[str] = Field(min_length=2, max_length=4)
    path1: str = Field(default="")
    path2: str = Field(default="")


class BrandCampaignResponse(BaseModel):
    """Stage 2b output — brand campaign skeleton for MID/GROWTH tiers."""

    brand_campaign_name: str
    brand_keywords: list[BrandKeywordItem] = Field(min_length=2, max_length=5)
    brand_ad: BrandAdItem


class SitelinkItem(BaseModel):
    """One sitelink in the extensions response.

    Truncation happens here via BeforeValidator so that Pydantic never rejects
    an LLM response that is slightly over the Google Ads character limits.
    The downstream assembly layer also slices, but this is the first gate.
    """

    link_text: Annotated[str, BeforeValidator(lambda v: str(v)[:25])]
    description1: Annotated[str, BeforeValidator(lambda v: str(v)[:35])]
    description2: Annotated[str, BeforeValidator(lambda v: str(v)[:35])]
    final_url: str = Field(default="https://example.com")


class ExtensionsResponse(BaseModel):
    """Stage 5 output — ad extensions."""

    sitelinks: list[SitelinkItem] = Field(min_length=2, max_length=4)
    callouts: list[str] = Field(min_length=4, max_length=8)
    structured_snippet_header: str
    structured_snippet_values: list[str] = Field(min_length=3, max_length=10)


# ---------------------------------------------------------------------------
# JSON extraction and parsing
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]+?)\s*```", re.IGNORECASE)


def _extract_json(raw: str) -> str:
    """Strip markdown code fences, returning the bare JSON string."""
    m = _JSON_FENCE_RE.search(raw)
    return m.group(1) if m else raw.strip()


def _parse_model(raw: str, model_cls: type[_T], stage: str) -> _T:  # noqa: UP047
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
You are an expert Google Ads consultant specialising in the Polish market.
Analyse the business description (which may be in Polish or English) and classify the vertical.

Polish vertical names and their English equivalents:
- salon / fryzjer / kosmetyczka / uroda → "salon"
- restauracja / kawiarnia / pizzeria / catering → "restaurant"
- kancelaria / prawnik / adwokat / radca prawny → "legal"
- lekarz / gabinet / dentysta / klinika / przychodnia → "medical"
- sklep internetowy / e-sklep / wysyłka → "ecommerce"
- nieruchomości / biuro nieruchomości / wynajem → "nieruchomości"
- szkoła / kurs / korepetycje / szkolenie → "edukacja"
- hydraulik / elektryk / sprzątanie / remont → "usługi domowe"

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
IMPORTANT: Follow the budget-tier structure constraints provided in the user prompt exactly.
The bidding strategy has been pre-selected — use it as-is, do not change it.
Prefer keywords with genuine search demand and commercial intent: favour the
specific terms real customers type (service + city, "near me", buying/booking
intent) over ultra-generic single words with little intent. Real search-volume
data is applied after this step, so concrete, high-intent keywords survive.
Structure each ad group by search intent and tag it with "intent_tier":
- HIGH_INTENT: ready-to-act terms (buy, book, hire, order, price, cost, "near me");
- MID_INTENT: research/comparison terms (best, top, review, compare, vs);
- DISCOVERY: broad informational terms (only for tiers that allow broad match).
Keep each ad group tightly themed (one intent tier, no keyword overlap between groups).
Do NOT put brand terms (the business's own name) in these ad groups — a separate
brand campaign handles those; set "is_brand" to false on every group here.
Respond ONLY with a valid JSON object matching this schema — no markdown, no prose:
{
  "campaign_name": "<string ≤ 120 chars>",
  "bidding_strategy": "<use the pre-selected strategy from the user prompt>",
  "ad_groups": [
    {
      "name": "<string>",
      "theme": "<short theme description>",
      "intent_tier": "HIGH_INTENT|MID_INTENT|DISCOVERY",
      "is_brand": false,
      "keywords": [
        { "text": "<string>", "match_type": "broad|phrase|exact", "estimated_cpc_pln": <float> }
      ]
    }
  ]
}"""

_AD_COPY_SYSTEM = """\
You are a senior Google Ads copywriter specialising in the Polish market.
Write 3 responsive search ad (RSA) variants for the given ad group.
STRICT character limits — Google Ads will reject longer copy:
  • Each headline: ≤ 30 characters (count carefully! Polish words are LONGER than English)
  • Each description: ≤ 90 characters (count carefully!)
  • path1 / path2: ≤ 15 characters each
Include at least 3 headlines and 2 descriptions per variant.
IMPORTANT — Polish language character lengths: words like "Zarezerwuj" (10), "Umów wizytę" (11),
"Skontaktuj się" (14) are safe for headlines. Avoid long compound words that exceed 30 chars.
Use Polish CTAs from this list:
  Call: Zadzwoń teraz, Zadzwoń, Umów rozmowę
  Book: Umów wizytę, Zarezerwuj, Umów się
  Buy:  Kup teraz, Zamów, Dodaj do koszyka
  Info: Sprawdź ofertę, Zobacz więcej, Dowiedz się więcej
  Sign: Zarejestruj się, Zapisz się, Dołącz
  Contact: Skontaktuj się, Napisz do nas, Zapytaj o cenę
  Offer: Poproś o wycenę, Pobierz ofertę, Uzyskaj rabat
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
You are a Google Ads negative keyword specialist for the Polish market.
Return a list of campaign-level negative keywords to block irrelevant searches.
Include: standard brand-safety negatives, vertical-specific negatives, and any
user-specified exclusions.  Use plain text only (no match-type syntax).

IMPORTANT — Polish standard negatives to always include at least one from each category:
- Free/darmowy: "darmowy", "za darmo", "bezpłatnie", "gratis"
- Job/praca: "praca", "oferty pracy", "rekrutacja", "kariera"
- DIY: "jak zrobić", "samodzielnie", "zrób sam", "poradnik"
- Education: "kurs", "szkolenie", "studia", "jak zrobić", "instrukcja"
- Forum/media: "youtube", "tiktok", "forum", "blog", "opinia"
- Download/pobieranie: "do pobrania", "filmik", "szablon", "wzór", "prezentacja"

Respond ONLY with valid JSON — no markdown, no prose:
{ "keywords": ["<string>", "…"] }"""

_BRAND_SYSTEM = """\
You are a Google Ads campaign architect specialising in brand campaigns.
Generate a separate Brand Search campaign for the business.
Use ONLY exact-match brand keywords (business name + common variations/misspellings).
Brand ads should be simple, trust-building copy mentioning the brand name.
STRICT character limits: headline ≤30 chars, description ≤90 chars, path ≤15 chars.
Brand campaign name must end with '| Brand Search'.
Respond ONLY with valid JSON — no markdown, no prose:
{
  "brand_campaign_name": "<business name> | Brand Search",
  "brand_keywords": [
    { "text": "<brand name>", "estimated_cpc_pln": <float> }
  ],
  "brand_ad": {
    "headlines": ["<≤30 chars>", "…"],
    "descriptions": ["<≤90 chars>", "<≤90 chars>"],
    "path1": "<≤15 chars>",
    "path2": "<≤15 chars>"
  }
}
Produce 2–5 brand keywords and exactly 3–5 headlines."""

_EXTENSIONS_SYSTEM = """\
You are a Google Ads extensions specialist.
Generate sitelinks, callouts, and one structured snippet for a business.
STRICT character limits (Google Ads will reject longer text):
• Sitelink link_text: ≤25 characters
• Sitelink description1/description2: ≤35 characters each
• Callout text: ≤25 characters each
• Structured snippet values: ≤25 characters each
Respond ONLY with valid JSON — no markdown, no prose:
{
  "sitelinks": [
    { "link_text": "<≤25 chars>", "description1": "<≤35 chars>", "description2": "<≤35 chars>", "final_url": "<url>" }
  ],
  "callouts": ["<≤25 chars>", "…"],
  "structured_snippet_header": "<e.g. Services>",
  "structured_snippet_values": ["<≤25 chars>", "…"]
}
Produce 2–4 sitelinks, 4–8 callouts, and 3–10 snippet values."""


# ---------------------------------------------------------------------------
# User-prompt builders
# ---------------------------------------------------------------------------


def _structure_user_prompt(
    brief: CampaignBrief,
    vertical: VerticalClassification,
    bidding_strategy: str,
    feedback: str | None = None,
    has_conversion_tracking: bool = False,
    existing_monthly_conversions: float = 0.0,
    competitors: list | None = None,
) -> str:
    tier = classify_budget_tier(brief.monthly_budget_pln)
    structure_fragment = build_structure_prompt_fragment(tier)
    lines = [
        f"Business description: {brief.business_description}",
        f"Location: {brief.location}",
        f"Primary action: {brief.primary_action}",
        f"Monthly budget: {brief.monthly_budget_pln} PLN",
        f"Typical customer value: {brief.typical_customer_value} PLN",
        f"Language: {brief.language}",
        f"Vertical: {vertical.vertical}",
        f"Pre-selected bidding strategy: {bidding_strategy}",
        "",
        structure_fragment,
    ]
    if vertical.sub_vertical:
        lines.append(f"Sub-vertical: {vertical.sub_vertical}")
    if brief.exclusions:
        lines.append(f"Exclusions: {', '.join(brief.exclusions)}")
    if competitors:
        comp_str = ", ".join(
            f"{c.domain} ({c.impression_share:.0%} udziału)" for c in competitors[:5]
        )
        lines.append(
            "\nKnown competitors already bidding on these searches: "
            f"{comp_str}. Favour differentiated, high-intent keywords where the "
            "business can realistically win the click; avoid head terms these "
            "competitors dominate."
        )
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
        has_conversion_tracking: bool = False,
        existing_monthly_conversions: float = 0.0,
        competitors: list | None = None,
    ) -> CampaignStructureResponse:
        """Stage 2 — design tier-aware campaign skeleton.

        Bidding strategy is resolved deterministically and injected into the
        prompt; the LLM's choice is overridden via model_copy().
        """
        tier = classify_budget_tier(brief.monthly_budget_pln)
        bidding_rec = resolve_bidding_strategy(
            tier, has_conversion_tracking, existing_monthly_conversions
        )
        resolved_strategy = bidding_rec.initial_strategy

        user = _structure_user_prompt(
            brief,
            vertical,
            resolved_strategy,
            feedback,
            has_conversion_tracking,
            existing_monthly_conversions,
            competitors,
        )
        response = await self._call_and_parse(
            _STRUCTURE_SYSTEM, user, "structure", CampaignStructureResponse, max_tokens=2000
        )
        # Always override the LLM's bidding choice with the deterministic one
        return response.model_copy(update={"bidding_strategy": resolved_strategy})

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

    async def generate_extensions(
        self,
        brief: CampaignBrief,
        vertical: VerticalClassification,
    ) -> ExtensionsResponse:
        """Stage 5 — generate sitelinks, callouts, and structured snippets."""
        user = (
            f"Business: {brief.business_description}\n"
            f"Vertical: {vertical.vertical}\n"
            f"Primary action: {brief.primary_action}\n"
            f"Language: {brief.language}\n"
            f"Location: {brief.location}"
        )
        return await self._call_and_parse(
            _EXTENSIONS_SYSTEM, user, "extensions", ExtensionsResponse, max_tokens=800
        )

    async def generate_brand_campaign(
        self,
        brief: CampaignBrief,
        main_campaign_name: str,
    ) -> BrandCampaignResponse:
        """Stage 2b — generate brand campaign skeleton for MID/GROWTH tiers."""
        user = (
            f"Business: {brief.business_description}\n"
            f"Main campaign name: {main_campaign_name}\n"
            f"Language: {brief.language}\n"
            f"Primary action: {brief.primary_action}"
        )
        return await self._call_and_parse(
            _BRAND_SYSTEM, user, "brand", BrandCampaignResponse, max_tokens=600
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
        extensions: ExtensionsResponse | None = None,
        brand: BrandCampaignResponse | None = None,
    ) -> CampaignProposal:
        """Combine pipeline outputs into a ``CampaignProposal`` domain object."""
        daily_budget_micros = int(brief.monthly_budget_pln / Decimal("30") * Decimal("1000000"))

        ad_groups: list[AdGroupProposal] = []
        all_cpcs: list[int] = []

        for ag_item, copy_resp in zip(structure.ad_groups, ad_copies):  # noqa: B905
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
                        avg_monthly_searches=kw.avg_monthly_searches,
                        intent_tier=ag_item.intent_tier,
                    )
                )

            ads: list[AdProposal] = []
            for variant in copy_resp.variants:
                ads.append(
                    AdProposal(
                        # Clamp to Google Ads hard limits so off-by-one LLM
                        # outputs never reach Rule 5 validation as errors.
                        headlines=[h[:30] for h in variant.headlines],
                        descriptions=[d[:90] for d in variant.descriptions],
                        final_url=_extract_url(brief),
                        path_segments=(variant.path1[:15], variant.path2[:15]),
                    )
                )

            ad_groups.append(
                AdGroupProposal(
                    name=ag_item.name,
                    keywords=keywords,
                    ads=ads,
                    intent_tier=ag_item.intent_tier,
                    is_brand=ag_item.is_brand,
                )
            )

        cpc_min = min(all_cpcs) if all_cpcs else 500_000
        cpc_max = max(all_cpcs) if all_cpcs else 2_000_000

        domain_sitelinks: list[SitelinkProposal] = []
        domain_callouts: list[CalloutProposal] = []
        domain_snippets: list[StructuredSnippetProposal] = []
        if extensions is not None:
            domain_sitelinks = [
                SitelinkProposal(
                    link_text=sl.link_text[:25],
                    description1=sl.description1[:35],
                    description2=sl.description2[:35],
                    final_url=sl.final_url,
                )
                for sl in extensions.sitelinks
            ]
            domain_callouts = [CalloutProposal(text=co[:25]) for co in extensions.callouts]
            if extensions.structured_snippet_values:
                domain_snippets = [
                    StructuredSnippetProposal(
                        header=extensions.structured_snippet_header,
                        values=[v[:25] for v in extensions.structured_snippet_values],
                    )
                ]

        # Brand campaign fields
        brand_campaign_name: str | None = None
        brand_keywords: list[KeywordProposal] = []
        brand_daily_budget_micros: int = 0
        brand_ad: AdProposal | None = None

        if brand is not None:
            brand_daily_budget_micros = max(1, int(daily_budget_micros * 0.1))
            brand_keywords = [
                KeywordProposal(
                    text=kw.text,
                    match_type=MatchType.EXACT,
                    estimated_cpc_micros=max(1, int(kw.estimated_cpc_pln * 1_000_000)),
                )
                for kw in brand.brand_keywords
            ]
            brand_campaign_name = brand.brand_campaign_name
            brand_ad = AdProposal(
                headlines=[h[:30] for h in brand.brand_ad.headlines],
                descriptions=[d[:90] for d in brand.brand_ad.descriptions],
                final_url=_extract_url(brief),
                path_segments=(brand.brand_ad.path1[:15], brand.brand_ad.path2[:15]),
            )

        return CampaignProposal(
            id=CampaignProposalId(str(uuid.uuid4())),
            brief_id=brief.id,
            campaign_name=structure.campaign_name,
            daily_budget_micros=daily_budget_micros,
            location_targeting=brief.location,
            bidding_strategy=structure.bidding_strategy,
            ad_groups=ad_groups,
            negative_keywords=negatives.keywords,
            sitelinks=domain_sitelinks,
            callouts=domain_callouts,
            structured_snippets=domain_snippets,
            estimated_cpc_range=(cpc_min, cpc_max),
            generated_at=datetime.now(UTC),
            brand_campaign_name=brand_campaign_name,
            brand_keywords=brand_keywords,
            brand_daily_budget_micros=brand_daily_budget_micros,
            brand_ad=brand_ad,
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
                user + f"\n\n[CORRECTION REQUIRED] Your previous response could not be "
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
