"""CieProposalEnhancer — make the generated campaign actually USE the CIE engine.

The whole point of the Campaign Intelligence Engine is that the campaign you
launch is built from intent-anchored keywords and angle-based hooks — not the
generic, product-anchored copy. This service runs the CIE keyword + hook engines
for a brief and rewrites the proposal's ad groups so the keywords are the
volume-backed intent/problem terms and the ads are the angle hooks.

Best-effort and fail-open: any error returns the original proposal unchanged, so
campaign generation never regresses if the CIE step has a hiccup.
"""

from __future__ import annotations

import dataclasses

import structlog

from adcopilot.application.ports.keyword_volume import VolumeRequestContext
from adcopilot.application.use_cases.campaign_intelligence.keywords.validate_keyword_volumes import (  # noqa: E501
    ValidateKeywordVolumesUseCase,
)
from adcopilot.config import Settings
from adcopilot.domain.campaign_intelligence.creatives import (
    angle_selector,
    hook_scorer,
    hook_selection,
    policy_screener,
)
from adcopilot.domain.campaign_intelligence.creatives.ad_surface import AdSurface
from adcopilot.domain.campaign_intelligence.creatives.angle import Angle
from adcopilot.domain.campaign_intelligence.creatives.hook_candidate import HookCandidate
from adcopilot.domain.campaign_intelligence.keywords import keyword_scorer
from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import KeywordCandidate
from adcopilot.domain.campaign_intelligence.keywords.value_objects import (
    KeywordIntent,
    SearchVolume,
)
from adcopilot.domain.campaign_intelligence.shared import dimension_selector
from adcopilot.domain.campaign_intelligence.shared.vertical import Vertical
from adcopilot.domain.launch.budget_tier import classify_budget_tier
from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CampaignBrief,
    CampaignProposal,
    KeywordProposal,
    MatchType,
)
from adcopilot.domain.launch.structure_rules import get_structure_config

logger = structlog.get_logger(__name__)

_KEYWORD_SLOTS = 30
_HOOK_SLOTS = 14
_MAX_HEADLINES = 15
_MAX_DESCRIPTIONS = 4
_MIN_HEADLINES = 3
_MIN_DESCRIPTIONS = 2
_DEFAULT_CPC_MICROS = 1_000_000

_INTENT_VALUES = [i.value for i in KeywordIntent]
_INTENT_TIER = {
    "PROBLEM": "HIGH_INTENT",
    "INTENT": "MID_INTENT",
    "BRAND": "HIGH_INTENT",
}


class CieProposalEnhancer:
    def __init__(self, settings: Settings, *, llm: object | None = None) -> None:
        self._settings = settings
        self._injected_llm = llm  # tests inject a fake; production builds its own

    async def enhance(
        self,
        proposal: CampaignProposal,
        brief: CampaignBrief,
        *,
        refresh_token: str | None = None,
        customer_id: str | None = None,
    ) -> CampaignProposal:
        if not self._settings.LLM_API_KEY:
            return proposal
        try:
            return await self._enhance(proposal, brief, refresh_token, customer_id)
        except Exception as exc:  # noqa: BLE001 — never regress campaign generation
            logger.warning(
                "cie.proposal_enhance.failed", brief_id=str(brief.id), error=str(exc)
            )
            return proposal

    async def _enhance(
        self,
        proposal: CampaignProposal,
        brief: CampaignBrief,
        refresh_token: str | None,
        customer_id: str | None,
    ) -> CampaignProposal:
        from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient

        service = brief.business_description
        vertical = Vertical.from_raw(getattr(brief, "vertical", None)).value.value
        language = brief.language or "pl"
        problems: list[str] = []  # the prompt infers from service + vertical

        owns_llm = self._injected_llm is None
        llm: object = self._injected_llm or AnthropicClient(
            api_key=self._settings.LLM_API_KEY or "", model=self._settings.LLM_MODEL_DEFAULT
        )
        try:
            ranked_by_intent = await self._cie_keywords(
                llm, service, vertical, problems, language, refresh_token, customer_id
            )
            headlines, descriptions = await self._cie_hooks(
                llm, service, vertical, problems, language
            )
        finally:
            if owns_llm:
                await llm.aclose()  # type: ignore[attr-defined]

        # Need a valid RSA (Google minima) to ship hooks as the ad.
        if len(headlines) < _MIN_HEADLINES or len(descriptions) < _MIN_DESCRIPTIONS:
            logger.info("cie.proposal_enhance.insufficient_hooks", brief_id=str(brief.id))
            return proposal

        template_ad = self._first_ad(proposal)
        final_url = template_ad.final_url if template_ad else ""
        paths = template_ad.path_segments if template_ad else ("", "")
        hook_ad = AdProposal(
            headlines=headlines[:_MAX_HEADLINES],
            descriptions=descriptions[:_MAX_DESCRIPTIONS],
            final_url=final_url,
            path_segments=paths,
        )

        cfg = get_structure_config(classify_budget_tier(brief.monthly_budget_pln))
        ad_groups = self._build_ad_groups(
            ranked_by_intent, hook_ad, cfg.min_keywords_per_group, cfg.max_keywords_per_group
        )
        if ad_groups:
            logger.info(
                "cie.proposal_enhance.applied",
                brief_id=str(brief.id),
                ad_groups=len(ad_groups),
                headlines=len(hook_ad.headlines),
            )
            return dataclasses.replace(proposal, ad_groups=ad_groups)

        # Not enough volume-backed keywords to rebuild groups — keep the base
        # keywords but still ship the angle hooks as the ad copy.
        logger.info("cie.proposal_enhance.hooks_only", brief_id=str(brief.id))
        return dataclasses.replace(
            proposal,
            ad_groups=[dataclasses.replace(ag, ads=[hook_ad]) for ag in proposal.ad_groups],
        )

    # -- keywords -----------------------------------------------------------

    async def _cie_keywords(
        self,
        llm: object,
        service: str,
        vertical: str,
        problems: list[str],
        language: str,
        refresh_token: str | None,
        customer_id: str | None,
    ) -> dict[str, list[KeywordCandidate]]:
        from adcopilot.infrastructure.adapters.claude_generation_adapter import (
            ClaudeKeywordGenerator,
        )
        from adcopilot.infrastructure.cie.wiring import (
            build_dataforseo_adapter,
            build_kp_volume_adapter,
            build_volume_cache,
        )

        allocation = dimension_selector.allocate(_KEYWORD_SLOTS, _INTENT_VALUES, {})
        generated = await ClaudeKeywordGenerator(llm).generate(  # type: ignore[arg-type]
            service=service,
            vertical=vertical,
            problems=problems,
            intent_allocation=allocation,
            language=language,
        )
        candidates = [
            KeywordCandidate(phrase=g.phrase, intent=KeywordIntent(g.intent), source="llm")
            for g in generated
        ]

        ctx = VolumeRequestContext(
            geo="PL", language=language, refresh_token=refresh_token, customer_id=customer_id
        )
        resolver = ValidateKeywordVolumesUseCase(
            cache=build_volume_cache(self._settings),
            primary=build_kp_volume_adapter(self._settings),
            fallback=build_dataforseo_adapter(self._settings),
            repo=None,  # type: ignore[arg-type] — resolve_volumes never touches the repo
        )
        try:
            volumes = await resolver.resolve_volumes([c.phrase for c in candidates], ctx)
        except Exception as exc:  # noqa: BLE001 — degrade to no-volume ranking
            logger.warning("cie.proposal_enhance.volume_lookup_failed", error=str(exc))
            volumes = {}

        for c in candidates:
            c.volume = volumes.get(c.phrase.strip().lower()) or SearchVolume(monthly_searches=0)
            c.score = keyword_scorer.compute_score(c.volume, c.intent.default_weight)

        by_intent: dict[str, list[KeywordCandidate]] = {v: [] for v in _INTENT_VALUES}
        seen: set[str] = set()
        for c in candidates:
            key = c.phrase.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            by_intent[c.intent.value].append(c)
        for group in by_intent.values():
            group.sort(
                key=lambda c: (
                    c.score.value if c.score else 0.0,
                    c.volume.monthly_searches if c.volume else 0,
                ),
                reverse=True,
            )
        return by_intent

    def _build_ad_groups(
        self,
        by_intent: dict[str, list[KeywordCandidate]],
        ad: AdProposal,
        min_kw: int,
        max_kw: int,
    ) -> list[AdGroupProposal]:
        problem = by_intent.get("PROBLEM", [])
        intent = by_intent.get("INTENT", [])
        brand = by_intent.get("BRAND", [])

        # Prefer two intent-anchored groups when each has enough keywords.
        if len(problem) >= min_kw and len(intent) >= min_kw:
            return [
                self._make_group("Problemy klientów", problem[:max_kw], ad, "HIGH_INTENT"),
                self._make_group("Intencja zakupowa", intent[:max_kw], ad, "MID_INTENT"),
            ]

        # Otherwise one combined group from the strongest intent/problem terms.
        pool = sorted(
            problem + intent + brand,
            key=lambda c: (c.score.value if c.score else 0.0, c.volume.monthly_searches if c.volume else 0),
            reverse=True,
        )
        if len(pool) >= min_kw:
            return [
                self._make_group(
                    "Słowa kluczowe oparte na intencji", pool[:max_kw], ad, "HIGH_INTENT"
                )
            ]
        return []

    @staticmethod
    def _make_group(
        name: str, candidates: list[KeywordCandidate], ad: AdProposal, tier: str
    ) -> AdGroupProposal:
        keywords = [
            KeywordProposal(
                text=c.phrase,
                match_type=MatchType.PHRASE,
                estimated_cpc_micros=(
                    c.volume.cpc_low_micros if c.volume and c.volume.cpc_low_micros else _DEFAULT_CPC_MICROS
                ),
                avg_monthly_searches=(
                    c.volume.monthly_searches if c.volume and c.volume.monthly_searches else None
                ),
                intent_tier=_INTENT_TIER.get(c.intent.value, tier),
            )
            for c in candidates
        ]
        return AdGroupProposal(
            name=name, keywords=keywords, ads=[ad], intent_tier=tier, is_brand=False
        )

    # -- hooks --------------------------------------------------------------

    async def _cie_hooks(
        self,
        llm: object,
        service: str,
        vertical: str,
        problems: list[str],
        language: str,
    ) -> tuple[list[str], list[str]]:
        from adcopilot.infrastructure.adapters.claude_hook_adapter import (
            ClaudeHookGenerator,
            ClaudeHookJudge,
        )

        allocation = angle_selector.allocate(_HOOK_SLOTS, {})
        surfaces = [AdSurface.HEADLINE.value, AdSurface.DESCRIPTION.value]
        generated = await ClaudeHookGenerator(llm).generate(  # type: ignore[arg-type]
            service=service,
            vertical=vertical,
            problems=problems,
            angle_allocation=allocation,
            surfaces=surfaces,
            language=language,
        )

        candidates: list[HookCandidate] = []
        for g in generated:
            try:
                angle = Angle(g.angle)
                candidates.append(
                    HookCandidate(
                        text=g.text,
                        angle=angle,
                        surface=AdSurface(g.surface),
                        policy=policy_screener.screen(g.text, angle),
                    )
                )
            except ValueError:
                continue
        if not candidates:
            return [], []

        # Judge is a second LLM pass; degrade to heuristic-only scores if it fails.
        by_text: dict[str, float] = {}
        try:
            results = await ClaudeHookJudge(llm).judge(  # type: ignore[arg-type]
                generated, service=service, vertical=vertical, language=language
            )
            by_text = {r.text: r.overall for r in results}
        except Exception as exc:  # noqa: BLE001
            logger.warning("cie.proposal_enhance.judge_failed", error=str(exc))

        for c in candidates:
            hook_scorer.score_candidate(c, judge=by_text.get(c.text, 0.5))

        selected = hook_selection.select_hooks(
            candidates, {AdSurface.HEADLINE: _MAX_HEADLINES, AdSurface.DESCRIPTION: _MAX_DESCRIPTIONS}
        )
        headlines = [c.text for c in selected if c.surface is AdSurface.HEADLINE]
        descriptions = [c.text for c in selected if c.surface is AdSurface.DESCRIPTION]
        return headlines, descriptions

    @staticmethod
    def _first_ad(proposal: CampaignProposal) -> AdProposal | None:
        for ag in proposal.ad_groups:
            if ag.ads:
                return ag.ads[0]
        return None
