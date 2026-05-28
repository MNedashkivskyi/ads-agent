"""Unit tests for the hybrid generation path in GenerateCampaignProposalUseCase (Task 1.5)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adcopilot.application.use_cases.launch.generate_proposal import GenerateCampaignProposalUseCase
from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.launch.entities import (
    CampaignBrief,
    CampaignBriefId,
    CampaignProposalId,
    LaunchStatus,
)
from adcopilot.infrastructure.llm.campaign_generator import (
    AdGroupCopyResponse,
    NegativeKeywordsResponse,
    RSAVariantItem,
)
from adcopilot.infrastructure.vertical_templates.yaml_adapter import YamlVerticalTemplateAdapter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_brief(budget: Decimal = Decimal("1200")) -> CampaignBrief:
    return CampaignBrief(
        id=CampaignBriefId(str(uuid.uuid4())),
        user_id=UserId(str(uuid.uuid4())),
        account_id=AccountId(str(uuid.uuid4())),
        business_description="Salon kosmetyczny oferujący manicure i pedicure",
        location="Kraków",
        typical_customer_value=Decimal("150"),
        primary_action="phone_call",
        monthly_budget_pln=budget,
        exclusions=[],
        language="pl",
        created_at=datetime.now(UTC),
        status=LaunchStatus.COLLECTING,
    )


def _make_copy_response() -> AdGroupCopyResponse:
    return AdGroupCopyResponse(
        variants=[
            RSAVariantItem(
                headlines=["Najlepszy salon {city}", "Rezerwacja online", "Sprawdź ofertę"],
                descriptions=[
                    "Profesjonalne usługi kosmetyczne w Twoim mieście.",
                    "Zadzwoń i umów się na wizytę już dziś.",
                ],
                path1="Salon",
                path2="",
            )
        ]
    )


def _make_negatives_response() -> NegativeKeywordsResponse:
    return NegativeKeywordsResponse(keywords=["kurs kosmetyczny", "allegro", "tanio"])


@pytest.fixture
def brief():
    return _make_brief()


@pytest.fixture
def template_repo():
    adapter = YamlVerticalTemplateAdapter()
    return adapter


@pytest.fixture
def mock_generator():
    gen = MagicMock()
    gen.generate_ad_copy = AsyncMock(return_value=_make_copy_response())
    gen.generate_negatives = AsyncMock(return_value=_make_negatives_response())
    gen.detect_vertical = AsyncMock()
    gen.build_structure = AsyncMock()
    return gen


@pytest.fixture
def mock_brief_repo():
    repo = MagicMock()
    repo.update_status = AsyncMock()
    return repo


@pytest.fixture
def mock_proposal_repo():
    repo = MagicMock()
    repo.save = AsyncMock(side_effect=lambda p: p)
    return repo


@pytest.fixture
def use_case(mock_brief_repo, mock_proposal_repo, mock_generator, template_repo):
    return GenerateCampaignProposalUseCase(
        brief_repo=mock_brief_repo,
        proposal_repo=mock_proposal_repo,
        generator=mock_generator,
        template_repo=template_repo,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHybridPathWithTemplateId:
    @pytest.mark.asyncio
    async def test_stages_1_and_2_skipped(self, use_case, mock_generator, brief):
        await use_case.execute(brief, template_id="beauty_salon")
        mock_generator.detect_vertical.assert_not_called()
        mock_generator.build_structure.assert_not_called()

    @pytest.mark.asyncio
    async def test_stage_3_ad_copy_still_runs(self, use_case, mock_generator, brief):
        await use_case.execute(brief, template_id="beauty_salon")
        assert mock_generator.generate_ad_copy.call_count > 0

    @pytest.mark.asyncio
    async def test_stage_4_negatives_still_runs(self, use_case, mock_generator, brief):
        await use_case.execute(brief, template_id="beauty_salon")
        mock_generator.generate_negatives.assert_called_once()

    @pytest.mark.asyncio
    async def test_proposal_has_template_keywords(self, use_case, brief):
        proposal = await use_case.execute(brief, template_id="beauty_salon")
        all_kws = [kw.text for ag in proposal.ad_groups for kw in ag.keywords]
        # Template should have Polish salon keywords (with city resolved)
        assert any("manicure" in kw.lower() or "paznokci" in kw.lower() for kw in all_kws)

    @pytest.mark.asyncio
    async def test_proposal_has_llm_ad_copy(self, use_case, brief):
        proposal = await use_case.execute(brief, template_id="beauty_salon")
        all_headlines = [h for ag in proposal.ad_groups for ad in ag.ads for h in ad.headlines]
        # LLM copy response has "Najlepszy salon {city}" headline
        assert any("Najlepszy" in h or "Rezerwacja" in h for h in all_headlines)

    @pytest.mark.asyncio
    async def test_llm_negatives_merged_with_template(self, use_case, brief):
        proposal = await use_case.execute(brief, template_id="beauty_salon")
        neg_lower = [n.lower() for n in proposal.negative_keywords]
        # Template negatives
        assert any("darmowy" in n for n in neg_lower)
        # LLM negatives from mock
        assert "kurs kosmetyczny" in proposal.negative_keywords

    @pytest.mark.asyncio
    async def test_proposal_saved_and_status_updated(
        self, use_case, mock_brief_repo, mock_proposal_repo, brief
    ):
        await use_case.execute(brief, template_id="beauty_salon")
        mock_proposal_repo.save.assert_called_once()
        mock_brief_repo.update_status.assert_called()


class TestFullLLMPathWhenTemplateIdIsNone:
    @pytest.mark.asyncio
    async def test_full_llm_path_runs_when_no_template_id(
        self, use_case, mock_generator, brief
    ):
        """When template_id=None, existing LLM pipeline should run unchanged."""
        # Mock the full pipeline
        from adcopilot.infrastructure.llm.campaign_generator import (
            CampaignStructureResponse,
            AdGroupItem,
            KeywordItem,
            VerticalClassification,
            ExtensionsResponse,
            SitelinkItem,
        )
        from adcopilot.domain.launch.entities import CampaignProposal

        mock_vertical = VerticalClassification(vertical="salon")
        mock_generator.detect_vertical.return_value = mock_vertical

        mock_structure = CampaignStructureResponse(
            campaign_name="Test Campaign",
            ad_groups=[
                AdGroupItem(
                    name="Test Group",
                    theme="test",
                    keywords=[
                        KeywordItem(text="test keyword 1"),
                        KeywordItem(text="test keyword 2"),
                        KeywordItem(text="test keyword 3"),
                    ],
                )
            ],
        )
        mock_generator.build_structure.return_value = mock_structure

        mock_extensions = ExtensionsResponse(
            sitelinks=[
                SitelinkItem(link_text="Test", description1="Desc1", description2="Desc2"),
                SitelinkItem(link_text="Test2", description1="Desc1", description2="Desc2"),
            ],
            callouts=["Callout 1", "Callout 2", "Callout 3", "Callout 4"],
            structured_snippet_header="Services",
            structured_snippet_values=["Svc1", "Svc2", "Svc3"],
        )
        mock_generator.generate_extensions = AsyncMock(return_value=mock_extensions)
        mock_generator.generate_brand_campaign = AsyncMock(side_effect=Exception("skip"))

        # Assemble a minimal valid proposal
        from adcopilot.application.services.template_proposal_assembler import TemplateProposalAssembler
        from adcopilot.infrastructure.vertical_templates.yaml_adapter import YamlVerticalTemplateAdapter
        _adapter = YamlVerticalTemplateAdapter()
        _tmpl = _adapter.get_default_template()
        _assembler = TemplateProposalAssembler()
        _base = _assembler.assemble(_tmpl, brief)
        mock_generator.assemble_proposal = MagicMock(return_value=_base)

        await use_case.execute(brief, template_id=None)

        mock_generator.detect_vertical.assert_called_once()
        mock_generator.build_structure.assert_called_once()


class TestFallbackWhenTemplateNotFound:
    @pytest.mark.asyncio
    async def test_falls_back_to_llm_when_template_missing(
        self, mock_brief_repo, mock_proposal_repo, mock_generator, brief
    ):
        """Unknown template_id falls through to the full LLM path."""
        # Build use_case with a template_repo that has no 'unknown_vertical'
        adapter = YamlVerticalTemplateAdapter()
        use_case = GenerateCampaignProposalUseCase(
            brief_repo=mock_brief_repo,
            proposal_repo=mock_proposal_repo,
            generator=mock_generator,
            template_repo=adapter,
        )
        # detect_vertical needs to return something for the LLM path
        from adcopilot.infrastructure.llm.campaign_generator import VerticalClassification
        mock_generator.detect_vertical.return_value = VerticalClassification(vertical="generic")

        from adcopilot.infrastructure.llm.campaign_generator import (
            CampaignStructureResponse,
            AdGroupItem,
            KeywordItem,
            ExtensionsResponse,
            SitelinkItem,
        )
        mock_generator.build_structure.return_value = CampaignStructureResponse(
            campaign_name="Fallback Campaign",
            ad_groups=[
                AdGroupItem(
                    name="Group",
                    theme="generic",
                    keywords=[KeywordItem(text=f"kw {i}") for i in range(3)],
                )
            ],
        )
        mock_generator.generate_extensions = AsyncMock(
            return_value=ExtensionsResponse(
                sitelinks=[
                    SitelinkItem(link_text="Link", description1="D1", description2="D2"),
                    SitelinkItem(link_text="Link2", description1="D1", description2="D2"),
                ],
                callouts=["C1", "C2", "C3", "C4"],
                structured_snippet_header="Svc",
                structured_snippet_values=["S1", "S2", "S3"],
            )
        )
        mock_generator.generate_brand_campaign = AsyncMock(side_effect=Exception("skip"))

        from adcopilot.application.services.template_proposal_assembler import TemplateProposalAssembler
        _base = TemplateProposalAssembler().assemble(adapter.get_default_template(), brief)
        mock_generator.assemble_proposal = MagicMock(return_value=_base)

        await use_case.execute(brief, template_id="unknown_vertical_xyz")

        # Falls through to LLM path
        mock_generator.detect_vertical.assert_called_once()
