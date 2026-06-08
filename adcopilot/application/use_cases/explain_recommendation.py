"""ExplainRecommendation use case: generates plain-language explanation via LLM."""

from __future__ import annotations

from typing import Any

import string

import structlog

from adcopilot.application.detection.templates import (
    ADVISORY_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    TEMPLATES,
    format_micros_as_currency,
)
from adcopilot.application.ports.llm import LLMClient
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.domain.recommendation import NON_EXECUTABLE_KINDS, RecommendationId

logger = structlog.get_logger(__name__)


class _SafeFormatter(string.Formatter):
    """Formatter that tolerates missing keys and bad format specs.

    Missing placeholders resolve to an empty string instead of raising
    ``KeyError`` — this prevents un-substituted tokens like ``{campaign_name}``
    (or the raw prompt template) from leaking into the LLM input and, in turn,
    into the user-facing explanation.
    """

    def get_value(self, key: object, args: object, kwargs: object) -> object:  # type: ignore[override]
        if isinstance(key, str):
            return kwargs.get(key, "")  # type: ignore[union-attr]
        return super().get_value(key, args, kwargs)  # type: ignore[arg-type]

    def format_field(self, value: object, format_spec: str) -> str:
        try:
            return super().format_field(value, format_spec)
        except (ValueError, TypeError):
            # e.g. ``{roas:.1f}`` when roas is missing (empty string)
            return str(value)


_FORMATTER = _SafeFormatter()


def _build_prompt(template: str, evidence: dict[str, object], savings: str) -> str:
    """Safely format a template with evidence values, never raising KeyError."""
    # Collect all format keys from evidence plus computed values
    fmt: dict[str, object] = {
        "savings": savings,
        # Common evidence aliases used across templates
        "search_term": evidence.get("search_term", ""),
        "clicks": evidence.get("clicks", 0),
        "cost": evidence.get("cost_micros", 0),
        "keyword": evidence.get("keyword_text", evidence.get("keyword", "")),
        "keyword_text": evidence.get("keyword_text", ""),
        "campaign": evidence.get("campaign_name", ""),
        "ad_group": evidence.get("ad_group_name", ""),
        "ad_id": evidence.get("ad_id", ""),
        "roas": evidence.get("roas", 0.0),
        "suggested_budget": evidence.get("suggested_budget_micros", 0),
        "bleed_pct": float(evidence.get("bleed_ratio", 0) or 0) * 100,  # type: ignore[arg-type]
        "impressions": evidence.get("impressions", 0),
        "conversions": evidence.get("conversions", 0),
    }
    # Also merge all evidence keys directly for maximum flexibility
    fmt.update({k: v for k, v in evidence.items() if k not in fmt})

    return _FORMATTER.format(template, **fmt)


def _economics_context_line(econ: Any | None) -> str:
    """A compact Polish business-context line for the explanation prompt, so the
    model frames the recommendation against the client's economics. Empty when
    no context is configured."""
    if econ is None or not getattr(econ, "is_context_configured", lambda: False)():
        return ""
    cur = getattr(econ, "currency_code", "PLN")
    parts: list[str] = []
    if getattr(econ, "primary_goal", None):
        parts.append(f"cel={econ.primary_goal}")
    if getattr(econ, "target_cpa", None) is not None:
        parts.append(f"docelowy CPA={econ.target_cpa:.0f} {cur}")
    if getattr(econ, "target_roas", None) is not None:
        parts.append(f"docelowy ROAS={econ.target_roas:.1f}x")
    if getattr(econ, "profit_margin_pct", None) is not None:
        parts.append(f"marża={econ.profit_margin_pct:.0f}%")
    if getattr(econ, "monthly_conversion_capacity", None) is not None:
        parts.append(f"miesięczna pojemność={econ.monthly_conversion_capacity} konwersji")
    if not parts:
        return ""
    return (
        "Kontekst biznesowy klienta: "
        + ", ".join(parts)
        + ". Odnieś rekomendację do tych celów (np. porównaj do docelowego CPA/ROAS)."
    )


class ExplainRecommendationUseCase:
    def __init__(self, llm: LLMClient, repo: RecommendationRepository) -> None:
        self._llm = llm
        self._repo = repo

    async def execute(
        self,
        recommendation_id: RecommendationId,
        language: str = "pl",
        business_context: Any | None = None,
    ) -> str:
        rec = await self._repo.get(recommendation_id)
        if rec is None:
            raise ValueError(f"Recommendation {recommendation_id} not found")

        savings_str = format_micros_as_currency(rec.estimated_monthly_savings_micros)
        template = (
            TEMPLATES.get(rec.kind, {}).get(language)
            or TEMPLATES.get(rec.kind, {}).get("en")
            or "Explain this recommendation: {evidence}"
        )
        user_prompt = _build_prompt(template, rec.evidence, savings_str)
        # Anchor the explanation to the client's economics so every rec is framed
        # against their goal/targets/margin, not just platform metrics.
        context_line = _economics_context_line(business_context)
        if context_line:
            user_prompt = f"{user_prompt}\n\n{context_line}"

        # Advisory (non-executable) recommendations have no Approve button, so the
        # explanation must not promise a one-click action ("Po zatwierdzeniu…").
        system_prompt = (
            ADVISORY_SYSTEM_PROMPT if rec.kind in NON_EXECUTABLE_KINDS else SYSTEM_PROMPT
        )
        explanation = await self._llm.complete(
            system=system_prompt,
            user=user_prompt,
            max_tokens=400,
            temperature=0.3,
        )

        await self._repo.update_explanation(recommendation_id, explanation)
        logger.info(
            "recommendation explained",
            rec_id=recommendation_id,
            kind=rec.kind.value,
            language=language,
        )
        return explanation
