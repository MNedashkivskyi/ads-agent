"""Unit tests for GenerateCampaignProposalUseCase.

Test strategy
-------------
All LLM calls are mocked with ``FakeLLMClient`` / ``ScriptedFakeLLMClient``.
Repository operations use in-memory fakes.  No database or network calls.

Test scenarios
--------------
1. Golden test — salon business (fixed LLM responses → valid proposal)
2. Golden test — e-commerce store (different vertical, higher budget)
3. LLM returns invalid JSON once, then valid JSON (retry and recover)
4. LLM returns invalid JSON twice (falls back to vertical template)
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from unittest.mock import AsyncMock, patch

from adcopilot.application.use_cases.launch.generate_proposal import (
    GenerateCampaignProposalUseCase,
)
from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.launch.entities import (
    CampaignBrief,
    CampaignBriefId,
    CampaignProposal,
    CampaignProposalId,
    LaunchStatus,
)
from adcopilot.domain.launch.validator import validate_proposal
from adcopilot.infrastructure.llm.campaign_generator import CampaignGenerator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_landing_page_checker():
    """Prevent real HTTP calls in unit tests — return a minimal passing result."""
    from adcopilot.infrastructure.landing_page.checker import LandingPageCheckResult

    def _make_ok(url: str) -> LandingPageCheckResult:
        return LandingPageCheckResult(
            url=url,
            reachable=True,
            https=True,
            load_time_seconds=0.5,
            language_detected=None,
            error_message=None,
            page_title=None,
            h1_text=None,
            body_text_sample=None,
        )

    async def _check(url: str) -> LandingPageCheckResult:
        return _make_ok(url)

    with patch(
        "adcopilot.infrastructure.landing_page.checker.LandingPageChecker",
        autospec=True,
    ) as MockChecker:
        MockChecker.return_value.check = AsyncMock(side_effect=_check)
        yield


# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------


class InMemoryBriefRepo:
    def __init__(self, brief: CampaignBrief) -> None:
        self._brief = brief
        self.status_history: list[LaunchStatus] = []

    async def get(self, brief_id: CampaignBriefId) -> CampaignBrief | None:
        return self._brief if str(self._brief.id) == str(brief_id) else None

    async def list_for_user(self, user_id: UserId) -> list[CampaignBrief]:
        return [self._brief]

    async def save(self, brief: CampaignBrief) -> CampaignBrief:
        self._brief = brief
        return brief

    async def update_status(self, brief_id: CampaignBriefId, status: LaunchStatus) -> None:
        self.status_history.append(status)


class InMemoryProposalRepo:
    def __init__(self) -> None:
        self._proposals: dict[str, CampaignProposal] = {}

    async def get(self, proposal_id: CampaignProposalId) -> CampaignProposal | None:
        return self._proposals.get(str(proposal_id))

    async def get_by_brief(self, brief_id: CampaignBriefId) -> CampaignProposal | None:
        for p in self._proposals.values():
            if p.brief_id == brief_id:
                return p
        return None

    async def save(self, proposal: CampaignProposal) -> CampaignProposal:
        self._proposals[str(proposal.id)] = proposal
        return proposal


# ---------------------------------------------------------------------------
# Scripted LLM client (returns responses from per-key queues)
# ---------------------------------------------------------------------------


class ScriptedFakeLLMClient:
    """Returns responses from per-stage queues, falling back to a default."""

    def __init__(
        self,
        queues: dict[str, list[str]],
        default: str = "{}",
    ) -> None:
        self._queues = {k: list(v) for k, v in queues.items()}
        self._default = default
        self.calls: list[dict] = []

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 400,
        temperature: float = 0.3,
    ) -> str:
        self.calls.append({"system": system, "user": user})
        for key, queue in self._queues.items():
            if key in system:
                if queue:
                    return queue.pop(0)
                break
        return self._default


# ---------------------------------------------------------------------------
# Golden-test fixture data
# ---------------------------------------------------------------------------

# --- Salon ---

_SALON_VERTICAL = json.dumps(
    {
        "vertical": "salon",
        "sub_vertical": "hair salon",
        "competitive_level": "medium",
        "language_hint": "en",
    }
)

_SALON_STRUCTURE = json.dumps(
    {
        "campaign_name": "Warsaw Hair Salon | Book Today",
        "bidding_strategy": "MAXIMIZE_CONVERSIONS",
        "ad_groups": [
            {
                "name": "Haircuts Warsaw",
                "theme": "haircut and styling services",
                "keywords": [
                    {"text": "hair salon Warsaw", "match_type": "phrase", "estimated_cpc_pln": 1.5},
                    {"text": "haircut Warsaw", "match_type": "phrase", "estimated_cpc_pln": 1.2},
                    {"text": "women haircut", "match_type": "broad", "estimated_cpc_pln": 0.9},
                    {"text": "hair cut near me", "match_type": "phrase", "estimated_cpc_pln": 1.3},
                    {"text": "best hair salon", "match_type": "broad", "estimated_cpc_pln": 1.1},
                    {"text": "hair salon booking", "match_type": "exact", "estimated_cpc_pln": 2.0},
                    {"text": "affordable haircut", "match_type": "phrase", "estimated_cpc_pln": 0.8},
                    {"text": "salon appointment", "match_type": "exact", "estimated_cpc_pln": 1.8},
                ],
            },
            {
                "name": "Hair Coloring",
                "theme": "hair color and highlights",
                "keywords": [
                    {"text": "hair color Warsaw", "match_type": "phrase", "estimated_cpc_pln": 2.0},
                    {"text": "hair highlights salon", "match_type": "broad", "estimated_cpc_pln": 1.6},
                    {"text": "balayage Warsaw", "match_type": "phrase", "estimated_cpc_pln": 2.5},
                    {"text": "ombre hair", "match_type": "phrase", "estimated_cpc_pln": 1.8},
                    {"text": "hair dye salon", "match_type": "broad", "estimated_cpc_pln": 1.2},
                    {"text": "root coloring service", "match_type": "exact", "estimated_cpc_pln": 2.2},
                    {"text": "professional coloring", "match_type": "phrase", "estimated_cpc_pln": 1.5},
                    {"text": "hair toning Warsaw", "match_type": "phrase", "estimated_cpc_pln": 1.9},
                ],
            },
        ],
    }
)

_SALON_AD_COPY = json.dumps(
    {
        "variants": [
            {
                "headlines": ["Warsaw Hair Salon", "Book Your Haircut Now", "Expert Stylists"],
                "descriptions": [
                    "Professional hair salon in Warsaw. Book online in 60 seconds.",
                    "Friendly stylists. Walk-ins and appointments welcome.",
                ],
                "path1": "HairSalon",
                "path2": "Warsaw",
            },
            {
                "headlines": ["Premium Hair Services", "Same Day Appointments", "Trusted Stylists"],
                "descriptions": [
                    "Quality cuts, color, and styling in Warsaw city center.",
                    "Over 500 happy clients. Book your slot online today.",
                ],
                "path1": "BookNow",
                "path2": "",
            },
            {
                "headlines": ["Affordable Hair Care", "Expert Color & Cuts", "Book Today"],
                "descriptions": [
                    "Hair salon with 5-star reviews in Warsaw. Great prices.",
                    "From cuts to color - we do it all. Online booking available.",
                ],
                "path1": "HairCare",
                "path2": "",
            },
        ]
    }
)

_SALON_NEGATIVES = json.dumps(
    {
        "keywords": [
            "diy hair",
            "hair extensions amazon",
            "free haircut",
            "hair wigs",
            "hair products online",
            "job",
            "tutorial",
        ]
    }
)


def _salon_brief() -> CampaignBrief:
    return CampaignBrief(
        id=CampaignBriefId(str(uuid.uuid4())),
        user_id=UserId(str(uuid.uuid4())),
        account_id=AccountId(str(uuid.uuid4())),
        business_description="Premium hair salon in Warsaw offering cuts, coloring, and styling",
        location="Warsaw, PL",
        typical_customer_value=Decimal("250"),
        primary_action="Book",
        monthly_budget_pln=Decimal("1000"),
        exclusions=["wigs", "extensions"],
        language="en",
        created_at=datetime.now(UTC),
        status=LaunchStatus.COLLECTING,
        interview_step=7,
    )


def _salon_llm() -> ScriptedFakeLLMClient:
    return ScriptedFakeLLMClient(
        {
            "classify the vertical": [_SALON_VERTICAL],
            "campaign skeleton": [_SALON_STRUCTURE],
            "copywriter": [_SALON_AD_COPY, _SALON_AD_COPY],  # two ad groups
            "negative keyword": [_SALON_NEGATIVES],
        }
    )


# --- E-commerce ---

_ECOM_VERTICAL = json.dumps(
    {
        "vertical": "e-commerce",
        "sub_vertical": "pet food",
        "competitive_level": "medium",
        "language_hint": "en",
    }
)

_ECOM_STRUCTURE = json.dumps(
    {
        "campaign_name": "Organic Pet Food | Shop Now",
        "bidding_strategy": "MAXIMIZE_CONVERSIONS",
        "ad_groups": [
            {
                "name": "Dog Food",
                "theme": "organic dog food products",
                "keywords": [
                    {"text": "organic dog food", "match_type": "phrase", "estimated_cpc_pln": 1.2},
                    {"text": "buy dog food online", "match_type": "phrase", "estimated_cpc_pln": 1.5},
                    {"text": "dog food delivery", "match_type": "broad", "estimated_cpc_pln": 0.9},
                    {"text": "premium dog food", "match_type": "phrase", "estimated_cpc_pln": 1.4},
                    {"text": "natural dog food", "match_type": "broad", "estimated_cpc_pln": 1.1},
                    {"text": "dog food Poland", "match_type": "phrase", "estimated_cpc_pln": 1.0},
                    {"text": "healthy dog food", "match_type": "broad", "estimated_cpc_pln": 1.3},
                    {"text": "grain free dog food", "match_type": "phrase", "estimated_cpc_pln": 1.6},
                ],
            },
            {
                "name": "Cat Food",
                "theme": "organic cat food products",
                "keywords": [
                    {"text": "organic cat food", "match_type": "phrase", "estimated_cpc_pln": 1.1},
                    {"text": "buy cat food online", "match_type": "phrase", "estimated_cpc_pln": 1.4},
                    {"text": "cat food delivery", "match_type": "broad", "estimated_cpc_pln": 0.8},
                    {"text": "premium cat food", "match_type": "phrase", "estimated_cpc_pln": 1.3},
                    {"text": "natural cat food", "match_type": "broad", "estimated_cpc_pln": 1.0},
                    {"text": "grain free cat food", "match_type": "phrase", "estimated_cpc_pln": 1.5},
                    {"text": "healthy cat food", "match_type": "broad", "estimated_cpc_pln": 1.2},
                    {"text": "wet cat food online", "match_type": "phrase", "estimated_cpc_pln": 0.9},
                ],
            },
        ],
    }
)

_ECOM_AD_COPY = json.dumps(
    {
        "variants": [
            {
                "headlines": ["Organic Pet Food", "Free Delivery Poland", "Shop Now & Save"],
                "descriptions": [
                    "Premium organic food for dogs and cats. Fast delivery in Poland.",
                    "Natural ingredients, happy pets. Shop our full range online today.",
                ],
                "path1": "PetFood",
                "path2": "Organic",
            },
            {
                "headlines": ["Best Pet Food Online", "Dogs & Cats Love It", "Order Today"],
                "descriptions": [
                    "100% natural pet food delivered to your door in Poland.",
                    "Trusted by thousands of pet owners. Order online for fast delivery.",
                ],
                "path1": "Shop",
                "path2": "PetFood",
            },
            {
                "headlines": ["Premium Dog & Cat Food", "Natural & Healthy", "Fast Delivery"],
                "descriptions": [
                    "Organic pet food with no artificial additives. Shop online now.",
                    "Keep your pet healthy with our natural food range. Free shipping.",
                ],
                "path1": "Organic",
                "path2": "Pets",
            },
        ]
    }
)

_ECOM_NEGATIVES = json.dumps(
    {
        "keywords": [
            "raw food recipes",
            "homemade pet food",
            "diy dog food",
            "free pet food",
            "pet food amazon",
            "job",
            "tutorial",
            "second hand",
        ]
    }
)


def _ecom_brief() -> CampaignBrief:
    return CampaignBrief(
        id=CampaignBriefId(str(uuid.uuid4())),
        user_id=UserId(str(uuid.uuid4())),
        account_id=AccountId(str(uuid.uuid4())),
        business_description=(
            "Online store selling organic pet food for dogs and cats in Poland"
        ),
        location="Poland",
        typical_customer_value=Decimal("150"),
        primary_action="Purchase",
        monthly_budget_pln=Decimal("2000"),
        exclusions=["raw food", "homemade"],
        language="en",
        created_at=datetime.now(UTC),
        status=LaunchStatus.COLLECTING,
        interview_step=7,
    )


def _ecom_llm() -> ScriptedFakeLLMClient:
    return ScriptedFakeLLMClient(
        {
            "classify the vertical": [_ECOM_VERTICAL],
            "campaign skeleton": [_ECOM_STRUCTURE],
            "copywriter": [_ECOM_AD_COPY, _ECOM_AD_COPY],  # two ad groups
            "negative keyword": [_ECOM_NEGATIVES],
        }
    )


# ---------------------------------------------------------------------------
# Helper: build use-case instance
# ---------------------------------------------------------------------------


def _make_use_case(
    brief: CampaignBrief,
    llm: ScriptedFakeLLMClient,
) -> tuple[GenerateCampaignProposalUseCase, InMemoryProposalRepo]:
    brief_repo = InMemoryBriefRepo(brief)
    proposal_repo = InMemoryProposalRepo()
    generator = CampaignGenerator(llm)
    uc = GenerateCampaignProposalUseCase(brief_repo, proposal_repo, generator)
    return uc, proposal_repo


# ---------------------------------------------------------------------------
# Test 1 — salon golden test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_salon_golden_proposal() -> None:
    """Full pipeline produces a valid proposal for a hair salon brief."""
    brief = _salon_brief()
    llm = _salon_llm()
    uc, proposal_repo = _make_use_case(brief, llm)

    proposal = await uc.execute(brief)

    # Persisted
    saved = await proposal_repo.get_by_brief(brief.id)
    assert saved is not None
    assert saved.id == proposal.id

    # Structure
    assert "Salon" in proposal.campaign_name or "Hair" in proposal.campaign_name
    assert len(proposal.ad_groups) == 2
    assert proposal.bidding_strategy == "MAXIMIZE_CLICKS"

    # Budget: 1000 PLN / 30 * 1_000_000 ≈ 33_333_333 micros
    expected_daily = int(Decimal("1000") / 30 * 1_000_000)
    assert abs(proposal.daily_budget_micros - expected_daily) < 10  # rounding

    # Keywords per group
    for ag in proposal.ad_groups:
        assert len(ag.keywords) >= 8, f"{ag.name} has only {len(ag.keywords)} keywords"

    # Ad copy limits (validator should catch any violation)
    errors = validate_proposal(proposal, brief)
    assert errors == [], f"Proposal failed validation: {errors}"

    # Negatives include LLM-generated ones
    assert len(proposal.negative_keywords) >= 3

    # Exclusions from brief propagated to negatives (via negatives stage)
    # (FakeLLM doesn't merge exclusions, but template fallback does)


@pytest.mark.asyncio
async def test_salon_golden_headline_length() -> None:
    """All headlines in a salon proposal respect the 30-char limit."""
    brief = _salon_brief()
    llm = _salon_llm()
    uc, _ = _make_use_case(brief, llm)
    proposal = await uc.execute(brief)

    for ag in proposal.ad_groups:
        for ad in ag.ads:
            for hl in ad.headlines:
                assert len(hl) <= 30, f"Headline too long ({len(hl)} chars): '{hl}'"
            for desc in ad.descriptions:
                assert len(desc) <= 90, f"Description too long ({len(desc)} chars): '{desc}'"


# ---------------------------------------------------------------------------
# Test 2 — e-commerce golden test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ecommerce_golden_proposal() -> None:
    """Full pipeline produces a valid proposal for an e-commerce brief."""
    brief = _ecom_brief()
    llm = _ecom_llm()
    uc, proposal_repo = _make_use_case(brief, llm)

    proposal = await uc.execute(brief)

    # Persisted
    saved = await proposal_repo.get_by_brief(brief.id)
    assert saved is not None

    # Structure
    assert len(proposal.ad_groups) == 2
    assert "Pet Food" in proposal.campaign_name or "Organic" in proposal.campaign_name

    # Budget: 2000 PLN / 30 * 1_000_000 ≈ 66_666_667 micros
    expected_daily = int(Decimal("2000") / 30 * 1_000_000)
    assert abs(proposal.daily_budget_micros - expected_daily) < 10

    # Location
    assert proposal.location_targeting == "Poland"

    # Validation
    errors = validate_proposal(proposal, brief)
    assert errors == [], f"E-commerce proposal failed: {errors}"

    # Each ad group has correct keyword count
    for ag in proposal.ad_groups:
        assert len(ag.keywords) == 8


@pytest.mark.asyncio
async def test_ecommerce_golden_cpc_range() -> None:
    """CPC range reflects the actual keyword estimates."""
    brief = _ecom_brief()
    llm = _ecom_llm()
    uc, _ = _make_use_case(brief, llm)
    proposal = await uc.execute(brief)

    cpc_min, cpc_max = proposal.estimated_cpc_range
    assert cpc_min > 0
    assert cpc_max >= cpc_min
    # Expected from our test data: 0.8–1.6 PLN → 800_000–1_600_000 micros
    assert cpc_min <= 1_000_000
    assert cpc_max >= 1_000_000


# ---------------------------------------------------------------------------
# Test 3 — LLM returns invalid JSON once, recovers on retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_json_retries_and_recovers() -> None:
    """When structure stage returns invalid JSON first, the generator retries and succeeds."""
    brief = _salon_brief()

    # Structure: first call → garbage, second call → valid JSON
    llm = ScriptedFakeLLMClient(
        {
            "classify the vertical": [_SALON_VERTICAL],
            "campaign skeleton": ["this is not valid json!!!", _SALON_STRUCTURE],
            "copywriter": [_SALON_AD_COPY, _SALON_AD_COPY],
            "negative keyword": [_SALON_NEGATIVES],
        }
    )
    uc, proposal_repo = _make_use_case(brief, llm)

    proposal = await uc.execute(brief)

    # Should have succeeded via the retry
    assert proposal is not None
    assert len(proposal.ad_groups) == 2

    # Validate the recovered proposal
    errors = validate_proposal(proposal, brief)
    assert errors == [], f"Recovered proposal failed validation: {errors}"

    # The LLM was called at least twice for the structure stage
    structure_calls = [c for c in llm.calls if "campaign skeleton" in c["system"]]
    assert len(structure_calls) == 2, (
        f"Expected 2 structure calls (initial + retry), got {len(structure_calls)}"
    )


@pytest.mark.asyncio
async def test_invalid_json_in_ad_copy_retries_and_recovers() -> None:
    """When ad-copy stage returns invalid JSON, it retries and produces a valid proposal."""
    brief = _salon_brief()

    # Ad copy: first call (for haircuts group) → invalid, retry → valid
    # Second call (for coloring group) → immediately valid
    llm = ScriptedFakeLLMClient(
        {
            "classify the vertical": [_SALON_VERTICAL],
            "campaign skeleton": [_SALON_STRUCTURE],
            "copywriter": ["{{bad json}}", _SALON_AD_COPY, _SALON_AD_COPY],
            "negative keyword": [_SALON_NEGATIVES],
        }
    )
    uc, _ = _make_use_case(brief, llm)

    proposal = await uc.execute(brief)

    assert proposal is not None
    errors = validate_proposal(proposal, brief)
    assert errors == [], f"Proposal after ad-copy retry failed: {errors}"

    copy_calls = [c for c in llm.calls if "copywriter" in c["system"]]
    # 3 = 2 (first group: bad+retry) + 1 (second group: direct)
    assert len(copy_calls) == 3


# ---------------------------------------------------------------------------
# Test 4 — LLM fails twice → template fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_double_failure_falls_back_to_template() -> None:
    """When structure stage always returns invalid JSON, use-case falls back to template."""
    brief = _salon_brief()

    # Structure always returns garbage → CampaignGenerator raises LLMError
    # → use case catches it and calls build_proposal_from_template
    llm = ScriptedFakeLLMClient(
        {
            "classify the vertical": [_SALON_VERTICAL],
            # Two bad responses (initial + retry) both fail to parse
            "campaign skeleton": ["NOT JSON AT ALL", "STILL NOT JSON"],
            "copywriter": [_SALON_AD_COPY],
            "negative keyword": [_SALON_NEGATIVES],
        }
    )
    uc, proposal_repo = _make_use_case(brief, llm)

    proposal = await uc.execute(brief)

    # Should have fallen back — proposal still valid
    assert proposal is not None
    assert proposal.brief_id == brief.id

    # Template for "salon" brief should produce salon-appropriate keywords
    all_kw_texts = {
        kw.text.lower()
        for ag in proposal.ad_groups
        for kw in ag.keywords
    }
    salon_kws = {"hair salon", "haircut near me", "hair color salon", "balayage"}
    assert any(kw in all_kw_texts for kw in salon_kws), (
        f"Expected salon keywords in template, got: {sorted(all_kw_texts)[:10]}"
    )

    # Template proposal passes validation
    errors = validate_proposal(proposal, brief)
    assert errors == [], f"Template proposal failed validation: {errors}"

    # Proposal was saved
    saved = await proposal_repo.get_by_brief(brief.id)
    assert saved is not None


@pytest.mark.asyncio
async def test_vertical_detection_failure_falls_back_to_template() -> None:
    """If the very first LLM call (vertical detection) fails twice, template is used."""
    brief = _ecom_brief()

    llm = ScriptedFakeLLMClient(
        {
            "classify the vertical": ["bad", "worse"],
        }
    )
    uc, _ = _make_use_case(brief, llm)

    proposal = await uc.execute(brief)

    # Template fallback should recognise "online store" keywords → ecommerce template
    assert proposal is not None
    assert proposal.brief_id == brief.id

    errors = validate_proposal(proposal, brief)
    assert errors == [], f"Template proposal failed validation: {errors}"


# ---------------------------------------------------------------------------
# Test 5 — Validator edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_template_proposal_always_passes_validator() -> None:
    """Every built-in template produces a proposal that passes the rule-based validator."""
    from adcopilot.domain.launch.templates import _TEMPLATES, build_proposal_from_template

    for vertical_key, tmpl in _TEMPLATES.items():  # noqa: B007
        # Build a brief that references this vertical
        desc_map = {
            "salon": "hair salon in Warsaw",
            "ecommerce": "online shop selling products",
            "restaurant": "restaurant near me",
            "legal": "law firm providing legal services",
            "medical": "medical clinic for doctors",
            "generic": "local business offering services",
        }
        brief = CampaignBrief(
            id=CampaignBriefId(str(uuid.uuid4())),
            user_id=UserId(str(uuid.uuid4())),
            account_id=AccountId(str(uuid.uuid4())),
            business_description=desc_map.get(vertical_key, "business"),
            location="Warsaw",
            typical_customer_value=Decimal("200"),
            primary_action="Call",
            monthly_budget_pln=Decimal("1500"),
            exclusions=[],
            language="en",
            created_at=datetime.now(UTC),
            status=LaunchStatus.COLLECTING,
            interview_step=7,
        )
        proposal = build_proposal_from_template(brief)
        errors = validate_proposal(proposal, brief)
        assert errors == [], (
            f"Template '{vertical_key}' failed validation: {errors}"
        )


@pytest.mark.asyncio
async def test_budget_respected_in_llm_proposal() -> None:
    """Daily budget in the generated proposal matches PLN monthly budget / 30."""
    brief = _salon_brief()  # 1000 PLN/month
    llm = _salon_llm()
    uc, _ = _make_use_case(brief, llm)

    proposal = await uc.execute(brief)

    expected = int(Decimal("1000") / 30 * 1_000_000)
    # Must be within 5% tolerance (as per validator)
    assert abs(proposal.daily_budget_micros - expected) / expected < 0.05


@pytest.mark.asyncio
async def test_status_transitions_on_success() -> None:
    """Brief status transitions COLLECTING → GENERATING → PROPOSED on success."""
    brief = _salon_brief()
    llm = _salon_llm()
    brief_repo = InMemoryBriefRepo(brief)
    proposal_repo = InMemoryProposalRepo()
    uc = GenerateCampaignProposalUseCase(brief_repo, proposal_repo, CampaignGenerator(llm))

    await uc.execute(brief)

    assert LaunchStatus.GENERATING in brief_repo.status_history
    assert brief_repo.status_history[-1] == LaunchStatus.PROPOSED


@pytest.mark.asyncio
async def test_status_transitions_on_template_fallback() -> None:
    """Brief status still reaches PROPOSED even when falling back to template."""
    brief = _salon_brief()
    llm = ScriptedFakeLLMClient(
        {"classify the vertical": ["bad", "also bad"]}
    )
    brief_repo = InMemoryBriefRepo(brief)
    proposal_repo = InMemoryProposalRepo()
    uc = GenerateCampaignProposalUseCase(brief_repo, proposal_repo, CampaignGenerator(llm))

    await uc.execute(brief)

    assert LaunchStatus.GENERATING in brief_repo.status_history
    assert brief_repo.status_history[-1] == LaunchStatus.PROPOSED


@pytest.mark.asyncio
async def test_raises_on_wrong_brief_status() -> None:
    """execute() raises ValueError if the brief is not COLLECTING or GENERATING."""
    brief = CampaignBrief(
        id=CampaignBriefId(str(uuid.uuid4())),
        user_id=UserId(str(uuid.uuid4())),
        account_id=AccountId(str(uuid.uuid4())),
        business_description="test",
        location="Warsaw",
        typical_customer_value=Decimal("100"),
        primary_action="Call",
        monthly_budget_pln=Decimal("500"),
        exclusions=[],
        language="en",
        created_at=datetime.now(UTC),
        status=LaunchStatus.PROPOSED,  # ← wrong status
        interview_step=7,
    )
    llm = ScriptedFakeLLMClient({})
    uc, _ = _make_use_case(brief, llm)

    with pytest.raises(ValueError, match="PROPOSED"):
        await uc.execute(brief)
