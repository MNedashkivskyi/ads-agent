"""The campaign proposal is rewritten to USE the CIE engine.

Asserts that the generated CampaignProposal gets dedicated intent/problem/brand ad
groups, each with its own (distinct) angle hooks and multiple RSA variants — and
that the result still passes the launch validator. Falls back to the base proposal
on error.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from adcopilot.config import Settings
from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.launch.entities import CampaignBrief, CampaignBriefId, LaunchStatus
from adcopilot.domain.launch.templates import build_proposal_from_template
from adcopilot.domain.launch.validator import validate_proposal
from adcopilot.infrastructure.cie.proposal_enhancer import CieProposalEnhancer

_INTENT_KW = [
    "drenaż limfatyczny", "modelowanie sylwetki", "masaż wyszczuplający",
    "ujędrnianie skóry", "redukcja cellulitu", "zabieg na cellulit",
    "wyszczuplanie ud", "masaż antycellulitowy",
]
_PROBLEM_KW = [
    "cellulit po ciąży", "nie mogę schudnąć z ud", "jak pozbyć się cellulitu",
    "oporny tłuszcz na brzuchu", "luźna skóra po schudnięciu", "cellulit na udach",
    "skóra pomarańczowa", "nierówna skóra na nogach",
]
_BRAND_KW = [
    "icoone warszawa", "icoone cena", "icoone tanio", "icoone opinie",
    "icoone zabieg", "icoone efekty", "icoone promocja", "icoone centrum",
]
_CIE_KEYWORDS = (
    [{"phrase": p, "intent": "INTENT"} for p in _INTENT_KW]
    + [{"phrase": p, "intent": "PROBLEM"} for p in _PROBLEM_KW]
    + [{"phrase": p, "intent": "BRAND"} for p in _BRAND_KW]
)

_PROBLEM_HOOKS = [
    {"text": "Cellulit, który nie znika?", "angle": "PAIN", "surface": "HEADLINE"},
    {"text": "Oporny tłuszcz na udach?", "angle": "PAIN", "surface": "HEADLINE"},
    {"text": "Diety i ćwiczenia zawiodły?", "angle": "FAILED_ALTERNATIVE", "surface": "HEADLINE"},
    {"text": "Kremy nie pomogły?", "angle": "FAILED_ALTERNATIVE", "surface": "HEADLINE"},
    {"text": "Znasz przyczynę cellulitu?", "angle": "CURIOSITY", "surface": "HEADLINE"},
    {"text": "Brzuch po ciąży?", "angle": "PAIN", "surface": "HEADLINE"},
    {"text": "Sport bez efektu?", "angle": "FAILED_ALTERNATIVE", "surface": "HEADLINE"},
    {"text": "Czemu cellulit wraca?", "angle": "CURIOSITY", "surface": "HEADLINE"},
    {"text": "Nierówna skóra na udach?", "angle": "PAIN", "surface": "HEADLINE"},
    {"text": "Drenaż limfatyczny celuje w przyczynę. Umów wizytę online.",
     "angle": "PAIN", "surface": "DESCRIPTION"},
    {"text": "Koniec z dietami bez efektu. Zobacz, co działa na cellulit.",
     "angle": "FAILED_ALTERNATIVE", "surface": "DESCRIPTION"},
    {"text": "Cellulit po ciąży? Zacznij od bezpłatnej konsultacji online.",
     "angle": "PAIN", "surface": "DESCRIPTION"},
]
_INTENT_HOOKS = [
    {"text": "Gładsza skóra w 4 tygodnie", "angle": "RESULT", "surface": "HEADLINE"},
    {"text": "Drenaż limfatyczny", "angle": "RESULT", "surface": "HEADLINE"},
    {"text": "Modelowanie sylwetki", "angle": "RESULT", "surface": "HEADLINE"},
    {"text": "Bez bólu i rekonwalescencji", "angle": "OBJECTION", "surface": "HEADLINE"},
    {"text": "Pierwsza konsultacja gratis", "angle": "OBJECTION", "surface": "HEADLINE"},
    {"text": "Zaufało nam 5000 klientek", "angle": "SOCIAL_PROOF", "surface": "HEADLINE"},
    {"text": "15 lat doświadczenia", "angle": "SOCIAL_PROOF", "surface": "HEADLINE"},
    {"text": "Ostatnie wolne terminy", "angle": "URGENCY", "surface": "HEADLINE"},
    {"text": "Zapisy na ten tydzień", "angle": "URGENCY", "surface": "HEADLINE"},
    {"text": "Drenaż limfatyczny i modelowanie sylwetki. Umów konsultację online.",
     "angle": "OBJECTION", "surface": "DESCRIPTION"},
    {"text": "Widoczny efekt po serii zabiegów. Bez bólu i rekonwalescencji.",
     "angle": "RESULT", "surface": "DESCRIPTION"},
    {"text": "Zaufało nam 5000 klientek. Zarezerwuj termin online już dziś.",
     "angle": "SOCIAL_PROOF", "surface": "DESCRIPTION"},
]


class _FakeLLM:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def complete(self, system: str, user: str, max_tokens: int = 400, temperature: float = 0.3) -> str:
        if self._fail:
            raise RuntimeError("LLM down")
        if "badania słów kluczowych" in system:
            return json.dumps(_CIE_KEYWORDS, ensure_ascii=False)
        if "copywriterem reklam" in system:
            if "frustracji" in user:  # problem-group focus marker
                return json.dumps(_PROBLEM_HOOKS, ensure_ascii=False)
            if "EFEKCIE" in user:  # intent-group focus marker
                return json.dumps(_INTENT_HOOKS, ensure_ascii=False)
            return json.dumps(_PROBLEM_HOOKS + _INTENT_HOOKS, ensure_ascii=False)
        return "[]"

    async def aclose(self) -> None:
        return None


def _brief() -> CampaignBrief:
    return CampaignBrief(
        id=CampaignBriefId(str(uuid.uuid4())),
        user_id=UserId(str(uuid.uuid4())),
        account_id=AccountId(str(uuid.uuid4())),
        business_description="Salon kosmetyczny — icoone, drenaż limfatyczny",
        location="Warszawa",
        typical_customer_value=Decimal("200"),
        primary_action="phone_call",
        monthly_budget_pln=Decimal("1500"),  # MID tier: ≥8 kw/group, ≤4 groups
        exclusions=[],
        language="pl",
        created_at=datetime.now(UTC),
        status=LaunchStatus.COLLECTING,
    )


async def test_proposal_gets_intent_problem_and_brand_groups() -> None:
    brief = _brief()
    base = build_proposal_from_template(brief)
    enhanced = await CieProposalEnhancer(Settings(LLM_API_KEY="k"), llm=_FakeLLM()).enhance(
        brief=brief, proposal=base
    )

    names = {ag.name for ag in enhanced.ad_groups}
    assert {"Problemy klientów", "Intencja zakupowa", "Marka"} <= names

    groups = {ag.name: ag for ag in enhanced.ad_groups}

    # Brand group: direct brand keywords + brand copy, flagged is_brand.
    brand = groups["Marka"]
    assert brand.is_brand
    assert any("icoone" in kw.text for kw in brand.keywords)
    assert any("Icoone" in h for ad in brand.ads for h in ad.headlines)

    # Each group ships multiple RSA variants with distinct headline sets.
    for name in ("Problemy klientów", "Intencja zakupowa"):
        ag = groups[name]
        assert len(ag.ads) >= 2, f"{name} should have multiple ads"
        headline_sets = [tuple(ad.headlines) for ad in ag.ads]
        assert len(set(headline_sets)) == len(headline_sets), f"{name} ads must differ"
        for ad in ag.ads:
            assert len(ad.headlines) >= 3 and len(ad.descriptions) >= 2

    # Headlines are tailored per group (problem-angle vs result/objection-angle).
    problem_headlines = {h for ad in groups["Problemy klientów"].ads for h in ad.headlines}
    intent_headlines = {h for ad in groups["Intencja zakupowa"].ads for h in ad.headlines}
    assert "Cellulit, który nie znika?" in problem_headlines
    assert "Gładsza skóra w 4 tygodnie" in intent_headlines
    assert "Cellulit, który nie znika?" not in intent_headlines  # distinct per group

    # Still a valid launchable proposal.
    assert validate_proposal(enhanced, brief) == []


async def test_keywords_are_intent_anchored() -> None:
    brief = _brief()
    base = build_proposal_from_template(brief)
    enhanced = await CieProposalEnhancer(Settings(LLM_API_KEY="k"), llm=_FakeLLM()).enhance(
        brief=brief, proposal=base
    )
    all_keywords = {kw.text for ag in enhanced.ad_groups for kw in ag.keywords}
    assert "drenaż limfatyczny" in all_keywords
    assert "cellulit po ciąży" in all_keywords


async def test_enhancer_removes_keyword_negative_conflicts() -> None:
    brief = _brief()
    base = build_proposal_from_template(brief)
    # Inject a negative that would block a brand keyword + a harmless one.
    base = dataclasses.replace(
        base, negative_keywords=[*base.negative_keywords, "icoone opinie", "praca"]
    )
    enhanced = await CieProposalEnhancer(Settings(LLM_API_KEY="k"), llm=_FakeLLM()).enhance(
        brief=brief, proposal=base
    )

    all_keywords = {kw.text.lower() for ag in enhanced.ad_groups for kw in ag.keywords}
    negatives = {n.lower() for n in enhanced.negative_keywords}
    assert "icoone opinie" in all_keywords  # the brand keyword is targeted
    assert "icoone opinie" not in negatives  # …so the conflicting negative is gone
    assert "praca" in negatives  # non-conflicting negatives are kept


def test_reconcile_negatives_unit() -> None:
    from adcopilot.domain.launch.entities import AdGroupProposal, MatchType, KeywordProposal
    from adcopilot.infrastructure.cie.proposal_enhancer import _reconcile_negatives

    ag = AdGroupProposal(
        name="Marka",
        keywords=[
            KeywordProposal(text="icoone opinie", match_type=MatchType.PHRASE, estimated_cpc_micros=0),
            KeywordProposal(text="icoone cena", match_type=MatchType.PHRASE, estimated_cpc_micros=0),
        ],
        ads=[],
    )
    kept = _reconcile_negatives(
        ["icoone opinie", "-ems opinie", "opinia", "praca", "tani icoone"], [ag]
    )
    assert "icoone opinie" not in kept  # blocks the keyword → removed
    assert "opinia" in kept  # 'opinia' ≠ 'opinie' → kept
    assert "praca" in kept
    assert "tani icoone" in kept  # no keyword has both tokens
    assert "-ems opinie" in kept  # no 'ems opinie' keyword


async def test_enhancer_falls_back_on_llm_failure() -> None:
    brief = _brief()
    base = build_proposal_from_template(brief)
    result = await CieProposalEnhancer(Settings(LLM_API_KEY="k"), llm=_FakeLLM(fail=True)).enhance(
        brief=brief, proposal=base
    )
    assert result is base


async def test_enhancer_noop_without_api_key() -> None:
    brief = _brief()
    base = build_proposal_from_template(brief)
    result = await CieProposalEnhancer(Settings(LLM_API_KEY=None), llm=_FakeLLM()).enhance(
        brief=brief, proposal=base
    )
    assert result is base
