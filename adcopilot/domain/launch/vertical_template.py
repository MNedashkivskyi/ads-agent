"""Domain entities for the vertical template engine (Phase 1).

These Pydantic models define the structure of a curated campaign template for
a specific business vertical (e.g. beauty salon, dental clinic). Templates are
loaded from YAML config files at startup by the infrastructure adapter and
drive the hybrid proposal generation path (template structure + LLM ad copy).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, model_validator


class CompetitiveLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class KeywordPriority(StrEnum):
    CORE = "core"
    EXTENDED = "extended"


class TemplateMatchType(StrEnum):
    EXACT = "EXACT"
    PHRASE = "PHRASE"
    BROAD = "BROAD"


class KeywordEntry(BaseModel):
    """A single keyword in a template keyword bank."""

    model_config = {"frozen": True}

    text: Annotated[str, Field(min_length=1)]
    match_type: TemplateMatchType
    priority: KeywordPriority = KeywordPriority.CORE


class TemplateAdGroup(BaseModel):
    """One ad group template within a vertical template."""

    model_config = {"frozen": True}

    name_template: Annotated[str, Field(min_length=1)]
    keyword_bank: Annotated[list[KeywordEntry], Field(min_length=1)]
    default_bid_modifier: float = 1.0

    @model_validator(mode="after")
    def _at_least_one_keyword(self) -> "TemplateAdGroup":
        if not self.keyword_bank:
            raise ValueError("keyword_bank must not be empty")
        return self


class TemplateNegativeList(BaseModel):
    """Campaign-level negative keyword lists for a vertical."""

    model_config = {"frozen": True}

    universal: list[str] = Field(default_factory=list)
    vertical_specific: list[str] = Field(default_factory=list)

    @property
    def all_negatives(self) -> list[str]:
        return self.universal + self.vertical_specific


class BudgetTierBiddingConfig(BaseModel):
    """Bidding configuration for a single budget tier."""

    model_config = {"frozen": True}

    bidding_strategy: Annotated[str, Field(min_length=1)]
    max_cpc_limit_pln: float
    daily_budget_ratio: Annotated[float, Field(gt=0, le=1)]


class TemplateBiddingDefaults(BaseModel):
    """Per-tier bidding defaults. All three tiers must be present."""

    model_config = {"frozen": True}

    micro: BudgetTierBiddingConfig
    mid: BudgetTierBiddingConfig
    growth: BudgetTierBiddingConfig

    def for_tier(self, tier: str) -> BudgetTierBiddingConfig:
        """Return the config for the given tier string (micro/mid/growth)."""
        return getattr(self, tier.lower())


class SitelinkTemplate(BaseModel):
    """A sitelink extension template."""

    model_config = {"frozen": True}

    text: Annotated[str, Field(max_length=25)]
    description1: Annotated[str, Field(max_length=35)] = ""
    description2: Annotated[str, Field(max_length=35)] = ""
    path: str = ""


class TemplateExtensionDefaults(BaseModel):
    """Default ad extension templates for a vertical."""

    model_config = {"frozen": True}

    sitelinks: list[SitelinkTemplate] = Field(default_factory=list)
    callouts: list[Annotated[str, Field(max_length=25)]] = Field(default_factory=list)
    structured_snippet_category: str = ""


class VerticalSummary(BaseModel):
    """Lightweight summary used for UI rendering (e.g. category grid)."""

    model_config = {"frozen": True}

    vertical_id: Annotated[str, Field(min_length=1)]
    display_name: Annotated[str, Field(min_length=1)]
    display_emoji: str = ""
    description: str = ""


class VerticalTemplate(BaseModel):
    """Full vertical campaign template loaded from a YAML config file."""

    model_config = {"frozen": True}

    vertical_id: Annotated[str, Field(min_length=1)]
    display_name: Annotated[str, Field(min_length=1)]
    display_emoji: str = ""
    language: str = "pl"
    competitive_level: CompetitiveLevel = CompetitiveLevel.MEDIUM

    ad_groups: Annotated[list[TemplateAdGroup], Field(min_length=1)]
    negatives: TemplateNegativeList = Field(default_factory=TemplateNegativeList)
    bidding_defaults: TemplateBiddingDefaults
    extensions: TemplateExtensionDefaults = Field(default_factory=TemplateExtensionDefaults)
    common_services: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _all_tiers_have_keywords(self) -> "VerticalTemplate":
        for ag in self.ad_groups:
            if len(ag.keyword_bank) < 1:
                raise ValueError(
                    f"Ad group '{ag.name_template}' must have at least one keyword"
                )
        return self

    def to_summary(self) -> VerticalSummary:
        return VerticalSummary(
            vertical_id=self.vertical_id,
            display_name=self.display_name,
            display_emoji=self.display_emoji,
        )
