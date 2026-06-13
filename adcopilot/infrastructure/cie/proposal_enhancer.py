"""CieProposalEnhancer — make the generated campaign actually USE the CIE engine.

The whole point of the Campaign Intelligence Engine is that the campaign you
launch is built from intent-anchored keywords and angle-based hooks. This service
rewrites the proposal's ad groups so that:

* keywords are the volume-backed intent/problem terms (and a dedicated **brand**
  group carries the direct brand keywords, e.g. "icoone warszawa");
* each group gets its **own** hooks (the problem group leans on pain angles, the
  intent group on result/objection angles, the brand group on brand copy);
* each group ships **multiple RSA variants** to review, not a single ad.

Best-effort and fail-open: any error returns the original proposal unchanged, so
campaign generation never regresses if the CIE step has a hiccup.
"""

from __future__ import annotations

import dataclasses
from collections import Counter

import structlog

from adcopilot.application.ports.keyword_volume import VolumeRequestContext
from adcopilot.application.use_cases.campaign_intelligence.keywords.validate_keyword_volumes import (  # noqa: E501
    ValidateKeywordVolumesUseCase,
)
from adcopilot.config import Settings
from adcopilot.domain.campaign_intelligence.creatives import hook_scorer, policy_screener
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
_HEADLINES_PER_ANGLE = 4
_MAX_RSA_VARIANTS = 3
_MAX_HEADLINES_PER_AD = 12
_MAX_DESCRIPTIONS_PER_AD = 4
_MIN_HEADLINES = 3
_MIN_DESCRIPTIONS = 2
_DEFAULT_CPC_MICROS = 1_000_000

_INTENT_VALUES = [i.value for i in KeywordIntent]
# Which angles each ad group's hooks lean on, so the headlines fit the group.
_PROBLEM_ANGLES = [Angle.PAIN, Angle.FAILED_ALTERNATIVE, Angle.CURIOSITY]
_INTENT_ANGLES = [Angle.RESULT, Angle.OBJECTION, Angle.SOCIAL_PROOF, Angle.URGENCY]
_ALL_ANGLES = list(Angle)
_HEADLINE_SURFACES = [AdSurface.HEADLINE.value, AdSurface.DESCRIPTION.value]


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
        city = brief.location or ""

        cfg = get_structure_config(classify_budget_tier(brief.monthly_budget_pln))
        min_kw, max_kw, max_groups = (
            cfg.min_keywords_per_group,
            cfg.max_keywords_per_group,
            cfg.max_ad_groups,
        )
        template_ad = self._first_ad(proposal)
        final_url = template_ad.final_url if template_ad else ""
        paths = template_ad.path_segments if template_ad else ("", "")

        owns_llm = self._injected_llm is None
        llm: object = self._injected_llm or AnthropicClient(
            api_key=self._settings.LLM_API_KEY or "", model=self._settings.LLM_MODEL_DEFAULT
        )
        groups: list[AdGroupProposal] = []
        hooks_only_ads: list[AdProposal] = []
        try:
            by_intent = await self._cie_keywords(
                llm, service, vertical, language, refresh_token, customer_id
            )
            problem = by_intent.get("PROBLEM", [])
            intent = by_intent.get("INTENT", [])
            brand = by_intent.get("BRAND", [])

            # Problem-anchored ad group with its own pain-angle hooks.
            if len(problem) >= min_kw:
                ads = await self._group_ads(
                    llm, service, vertical, language,
                    focus=_problem_focus(problem), angles=_PROBLEM_ANGLES,
                    final_url=final_url, paths=paths,
                )
                if ads:
                    groups.append(self._make_group("Problemy klientów", problem[:max_kw], ads, "HIGH_INTENT"))

            # Intent-anchored ad group with result/objection-angle hooks.
            if len(intent) >= min_kw:
                ads = await self._group_ads(
                    llm, service, vertical, language,
                    focus=_intent_focus(intent), angles=_INTENT_ANGLES,
                    final_url=final_url, paths=paths,
                )
                if ads:
                    groups.append(self._make_group("Intencja zakupowa", intent[:max_kw], ads, "MID_INTENT"))

            # Dedicated brand ad group with direct brand keywords + brand copy.
            brand_group = self._brand_group(brand, city, final_url, paths, min_kw, max_kw)
            if brand_group is not None:
                groups.append(brand_group)

            # Fallback: not enough keywords for themed groups → one combined group.
            if not groups:
                pool = _sorted(problem + intent + brand)
                ads = await self._group_ads(
                    llm, service, vertical, language,
                    focus=None, angles=_ALL_ANGLES,
                    final_url=final_url, paths=paths,
                )
                if ads and len(pool) >= min_kw:
                    groups = [
                        self._make_group("Słowa kluczowe oparte na intencji", pool[:max_kw], ads, "HIGH_INTENT")
                    ]
                elif ads:
                    hooks_only_ads = ads  # swap base ads for hooks, keep base keywords
        finally:
            if owns_llm:
                await llm.aclose()  # type: ignore[attr-defined]

        if groups:
            groups = groups[:max_groups]
            # Drop any campaign negative that would block one of our keywords —
            # a keyword and a negative for the same term is a conflict (the
            # keyword would never serve). E.g. dropping "-icoone opinie" when the
            # brand group bids on "icoone opinie".
            negatives = _reconcile_negatives(proposal.negative_keywords, groups)
            removed = len(proposal.negative_keywords) - len(negatives)
            logger.info(
                "cie.proposal_enhance.applied",
                brief_id=str(brief.id),
                ad_groups=len(groups),
                ads_per_group=[len(g.ads) for g in groups],
                negatives_removed=removed,
            )
            return dataclasses.replace(
                proposal, ad_groups=groups, negative_keywords=negatives
            )

        if hooks_only_ads:
            logger.info("cie.proposal_enhance.hooks_only", brief_id=str(brief.id))
            return dataclasses.replace(
                proposal,
                ad_groups=[dataclasses.replace(ag, ads=hooks_only_ads) for ag in proposal.ad_groups],
            )

        logger.info("cie.proposal_enhance.no_change", brief_id=str(brief.id))
        return proposal

    # -- keywords -----------------------------------------------------------

    async def _cie_keywords(
        self,
        llm: object,
        service: str,
        vertical: str,
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
            service=service, vertical=vertical, problems=[], intent_allocation=allocation, language=language,
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
            group.sort(key=_kw_sort_key, reverse=True)
        return by_intent

    @staticmethod
    def _make_group(
        name: str, candidates: list[KeywordCandidate], ads: list[AdProposal], tier: str
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
                intent_tier=tier,
            )
            for c in candidates
        ]
        return AdGroupProposal(name=name, keywords=keywords, ads=ads, intent_tier=tier, is_brand=False)

    # -- hooks --------------------------------------------------------------

    async def _group_ads(
        self,
        llm: object,
        service: str,
        vertical: str,
        language: str,
        *,
        focus: str | None,
        angles: list[Angle],
        final_url: str,
        paths: tuple[str, str],
    ) -> list[AdProposal]:
        headlines, descriptions = await self._cie_hooks(
            llm, service, vertical, language, focus, angles
        )
        return _build_rsas(headlines, descriptions, final_url, paths)

    async def _cie_hooks(
        self,
        llm: object,
        service: str,
        vertical: str,
        language: str,
        focus: str | None,
        angles: list[Angle],
    ) -> tuple[list[str], list[str]]:
        from adcopilot.infrastructure.adapters.claude_hook_adapter import ClaudeHookGenerator

        allocation = {a.value: _HEADLINES_PER_ANGLE for a in angles}
        try:
            generated = await ClaudeHookGenerator(llm).generate(  # type: ignore[arg-type]
                service=service, vertical=vertical, problems=[],
                angle_allocation=allocation, surfaces=_HEADLINE_SURFACES,
                language=language, focus=focus,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("cie.proposal_enhance.hook_gen_failed", error=str(exc))
            return [], []

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
        for c in candidates:
            hook_scorer.score_candidate(c, judge=0.6)

        headlines = _dedup_sorted(candidates, AdSurface.HEADLINE)
        descriptions = _dedup_sorted(candidates, AdSurface.DESCRIPTION)
        return headlines, descriptions

    # -- brand --------------------------------------------------------------

    def _brand_group(
        self,
        brand_kws: list[KeywordCandidate],
        city: str,
        final_url: str,
        paths: tuple[str, str],
        min_kw: int,
        max_kw: int,
    ) -> AdGroupProposal | None:
        if len(brand_kws) < min_kw:
            return None
        brand = _extract_brand_name(brand_kws)
        if not brand:
            return None
        headlines = _brand_headlines(brand, city)
        descriptions = _brand_descriptions(brand)
        ads = _build_rsas(headlines, descriptions, final_url, paths)
        if not ads:
            return None
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
                intent_tier="HIGH_INTENT",
            )
            for c in brand_kws[:max_kw]
        ]
        return AdGroupProposal(
            name="Marka", keywords=keywords, ads=ads, intent_tier="HIGH_INTENT", is_brand=True
        )

    @staticmethod
    def _first_ad(proposal: CampaignProposal) -> AdProposal | None:
        for ag in proposal.ad_groups:
            if ag.ads:
                return ag.ads[0]
        return None


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _reconcile_negatives(
    negatives: list[str], ad_groups: list[AdGroupProposal]
) -> list[str]:
    """Remove negatives that would block any keyword in the new ad groups.

    A negative blocks a keyword when all of the negative's tokens appear in the
    keyword (phrase/broad-negative semantics). Keeping both is a self-defeating
    conflict, so the negative is dropped in favour of the deliberately-targeted
    keyword.
    """
    keyword_token_sets = [
        set(kw.text.lower().split()) for ag in ad_groups for kw in ag.keywords
    ]
    kept: list[str] = []
    for neg in negatives:
        neg_tokens = set(neg.lower().lstrip("-").split())
        if neg_tokens and any(neg_tokens <= kt for kt in keyword_token_sets):
            continue  # conflicts with a keyword → drop it
        kept.append(neg)
    return kept


def _kw_sort_key(c: KeywordCandidate) -> tuple[float, int]:
    return (
        c.score.value if c.score else 0.0,
        c.volume.monthly_searches if c.volume else 0,
    )


def _sorted(candidates: list[KeywordCandidate]) -> list[KeywordCandidate]:
    return sorted(candidates, key=_kw_sort_key, reverse=True)


def _dedup_sorted(candidates: list[HookCandidate], surface: AdSurface) -> list[str]:
    items = sorted(
        (c for c in candidates if c.surface is surface),
        key=lambda c: c.final_score,
        reverse=True,
    )
    out: list[str] = []
    seen: set[str] = set()
    for c in items:
        key = c.text.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c.text)
    return out


def _build_rsas(
    headlines: list[str],
    descriptions: list[str],
    final_url: str,
    paths: tuple[str, str],
    max_variants: int = _MAX_RSA_VARIANTS,
) -> list[AdProposal]:
    """Build up to ``max_variants`` distinct RSAs from a hook pool.

    Headlines are round-robined across variants so each ad reviews a different
    set; descriptions rotate likewise. Each RSA respects Google's RSA minima.
    """
    if len(headlines) < _MIN_HEADLINES or len(descriptions) < _MIN_DESCRIPTIONS:
        return []
    n = min(max_variants, max(1, len(headlines) // _MIN_HEADLINES))
    rsas: list[AdProposal] = []
    for i in range(n):
        chunk = headlines[i::n]
        if len(chunk) < _MIN_HEADLINES:
            extra = [h for h in headlines if h not in chunk]
            chunk = (chunk + extra)[: max(_MIN_HEADLINES, len(chunk))]
        chunk = chunk[:_MAX_HEADLINES_PER_AD]

        dchunk = descriptions[i::n] if len(descriptions) >= _MIN_DESCRIPTIONS * n else list(descriptions)
        if len(dchunk) < _MIN_DESCRIPTIONS:
            dchunk = (descriptions + descriptions)[i : i + _MIN_DESCRIPTIONS]
        dchunk = dchunk[:_MAX_DESCRIPTIONS_PER_AD]

        if len(chunk) >= _MIN_HEADLINES and len(dchunk) >= _MIN_DESCRIPTIONS:
            rsas.append(
                AdProposal(
                    headlines=chunk, descriptions=dchunk, final_url=final_url, path_segments=paths
                )
            )
    return rsas


def _problem_focus(problem_kws: list[KeywordCandidate]) -> str:
    sample = ", ".join(c.phrase for c in problem_kws[:6])
    return (
        "Skup się na bólu, frustracji i KONKRETNYM problemie klienta. Klient "
        f"opisuje to m.in. tak: {sample}. Nazywaj problem dosłownie — bez "
        "ogólnych pytań typu 'Czy to boli?'."
    )


def _intent_focus(intent_kws: list[KeywordCandidate]) -> str:
    sample = ", ".join(c.phrase for c in intent_kws[:6])
    return (
        "Skup się na pożądanym EFEKCIE, korzyściach i powodach wyboru tej firmy. "
        f"Klient szuka m.in.: {sample}. Możesz nawiązać do nazwy usługi i efektu."
    )


def _extract_brand_name(brand_kws: list[KeywordCandidate]) -> str | None:
    first_tokens = [c.phrase.split()[0] for c in brand_kws if c.phrase.split()]
    if not first_tokens:
        return None
    token = Counter(first_tokens).most_common(1)[0][0]
    return token[:20].title() if token else None


def _brand_headlines(brand: str, city: str) -> list[str]:
    candidates = [
        f"{brand} {city}".strip(),
        f"{brand} — umów wizytę",
        f"{brand} — sprawdź ofertę",
        f"Zarezerwuj wizytę w {brand}",
        f"{brand} — cennik i opinie",
        f"{brand} — zapisy online",
        f"Wybierz {brand}",
        "Umów się online już dziś",
    ]
    return [h for h in candidates if 0 < len(h) <= 30][:_MAX_HEADLINES_PER_AD]


def _brand_descriptions(brand: str) -> list[str]:
    candidates = [
        f"Profesjonalne zabiegi {brand}. Umów wizytę online — szybko i wygodnie.",
        f"Sprawdź ofertę i ceny {brand}. Zarezerwuj termin już dziś.",
        f"{brand} — zaufaj specjalistom. Bezpłatna konsultacja i jasne ceny.",
    ]
    return [d for d in candidates if 0 < len(d) <= 90][:_MAX_DESCRIPTIONS_PER_AD]
