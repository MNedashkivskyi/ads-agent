"""The campaign proposal is rewritten to USE the CIE engine.

Asserts that, given CIE keyword + hook generation, the generated CampaignProposal's
ad groups carry the intent-anchored keywords and the ads carry the angle hooks —
and that the result still passes the launch validator. Falls back to the base
proposal when the CIE step errors.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from adcopilot.config import Settings
from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.launch.entities import CampaignBrief, CampaignBriefId, LaunchStatus
from adcopilot.domain.launch.templates import build_proposal_from_template
from adcopilot.domain.launch.validator import validate_proposal
from adcopilot.infrastructure.cie.proposal_enhancer import CieProposalEnhancer

# Distinct CIE keyword + hook outputs so we can assert they reached the proposal.
_CIE_KEYWORDS = [
    {"phrase": "drenaż limfatyczny", "intent": "INTENT"},
    {"phrase": "modelowanie sylwetki", "intent": "INTENT"},
    {"phrase": "masaż wyszczuplający", "intent": "INTENT"},
    {"phrase": "cellulit po ciąży", "intent": "PROBLEM"},
    {"phrase": "nie mogę schudnąć z ud", "intent": "PROBLEM"},
    {"phrase": "jak pozbyć się cellulitu", "intent": "PROBLEM"},
    {"phrase": "oporny tłuszcz na brzuchu", "intent": "PROBLEM"},
    {"phrase": "icoone warszawa", "intent": "BRAND"},
]
_CIE_HOOKS = [
    {"text": "Cellulit, który nie znika?", "angle": "PAIN", "surface": "HEADLINE"},
    {"text": "Diety nie pomogły?", "angle": "FAILED_ALTERNATIVE", "surface": "HEADLINE"},
    {"text": "Gładsza skóra w 4 tygodnie", "angle": "RESULT", "surface": "HEADLINE"},
    {"text": "Zaufało nam 5000 klientek", "angle": "SOCIAL_PROOF", "surface": "HEADLINE"},
    {"text": "Ostatnie wolne terminy", "angle": "URGENCY", "surface": "HEADLINE"},
    {
        "text": "Drenaż limfatyczny i modelowanie sylwetki bez bólu i rekonwalescencji.",
        "angle": "OBJECTION",
        "surface": "DESCRIPTION",
    },
    {
        "text": "Widoczny efekt po serii zabiegów. Umów bezpłatną konsultację.",
        "angle": "RESULT",
        "surface": "DESCRIPTION",
    },
    {
        "text": "Pozbądź się cellulitu po ciąży. Sprawdzona metoda, realne rezultaty.",
        "angle": "PAIN",
        "surface": "DESCRIPTION",
    },
]


class _FakeLLM:
    """Returns canned JSON per call, keyed by a distinctive system-prompt phrase."""

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def complete(self, system: str, user: str, max_tokens: int = 400, temperature: float = 0.3) -> str:
        import json

        if self._fail:
            raise RuntimeError("LLM down")
        if "badania słów kluczowych" in system:
            return json.dumps(_CIE_KEYWORDS, ensure_ascii=False)
        if "copywriterem reklam" in system:
            return json.dumps(_CIE_HOOKS, ensure_ascii=False)
        if "jurorem" in system:
            return json.dumps(
                [
                    {"text": h["text"], "specificity": 0.8, "tension": 0.8,
                     "pain_truth": 0.8, "clarity": 0.8}
                    for h in _CIE_HOOKS
                ],
                ensure_ascii=False,
            )
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
        monthly_budget_pln=Decimal("1500"),
        exclusions=[],
        language="pl",
        created_at=datetime.now(UTC),
        status=LaunchStatus.COLLECTING,
    )


def _settings() -> Settings:
    return Settings(LLM_API_KEY="test-key")


async def test_proposal_uses_cie_keywords_and_hooks() -> None:
    brief = _brief()
    base = build_proposal_from_template(brief)

    enhancer = CieProposalEnhancer(_settings(), llm=_FakeLLM())
    enhanced = await enhancer.enhance(brief=brief, proposal=base)

    # Keywords: the proposal's ad groups now carry the intent-anchored terms.
    all_keywords = {kw.text for ag in enhanced.ad_groups for kw in ag.keywords}
    assert "drenaż limfatyczny" in all_keywords
    assert "cellulit po ciąży" in all_keywords

    # Ads: every ad's headlines/descriptions are the angle hooks.
    all_headlines = {h for ag in enhanced.ad_groups for ad in ag.ads for h in ad.headlines}
    assert "Cellulit, który nie znika?" in all_headlines
    sample_ad = enhanced.ad_groups[0].ads[0]
    assert any("bez bólu" in d for d in sample_ad.descriptions)

    # The rewritten proposal is still valid for launch.
    errors = validate_proposal(enhanced, brief)
    assert errors == [], errors


async def test_enhancer_falls_back_on_llm_failure() -> None:
    brief = _brief()
    base = build_proposal_from_template(brief)
    enhancer = CieProposalEnhancer(_settings(), llm=_FakeLLM(fail=True))
    result = await enhancer.enhance(brief=brief, proposal=base)
    # Unchanged base proposal — generation never regresses on a CIE hiccup.
    assert result is base


async def test_enhancer_noop_without_api_key() -> None:
    brief = _brief()
    base = build_proposal_from_template(brief)
    enhancer = CieProposalEnhancer(Settings(LLM_API_KEY=None), llm=_FakeLLM())
    result = await enhancer.enhance(brief=brief, proposal=base)
    assert result is base
