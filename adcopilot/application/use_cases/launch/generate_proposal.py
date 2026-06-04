"""GenerateCampaignProposalUseCase — 5-stage LLM pipeline.

Pipeline
--------
1. Vertical detection   — classify the business into a vertical.
2. Campaign structure   — design the campaign skeleton (ad groups + keywords).
3. Ad copy              — generate RSA variants per ad group.
4. Negative keywords    — suggest campaign-level negatives.
5. Validation + retry   — rule-based check; on failure rebuild affected stages
                          with error feedback; template fallback after two failures.

Token budget: ≤ 60 000 input + 20 000 output tokens across all LLM calls
(tracked in ``CampaignGenerator``).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from adcopilot.application.ports.keyword_planner import KeywordPlannerPort

from adcopilot.application.detection.validation import LandingPageCheckResult as DetectionLPResult
from adcopilot.application.detection.validation import ValidationContext, validate_proposal
from adcopilot.application.ports.launch_repositories import (
    CampaignBriefRepo,
    CampaignProposalRepo,
)
from adcopilot.application.ports.vertical_template_repository import VerticalTemplateRepository
from adcopilot.application.services.template_proposal_assembler import TemplateProposalAssembler
from adcopilot.domain.exceptions import LLMError
from adcopilot.domain.launch.budget_tier import BudgetTier, classify_budget_tier
from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CampaignBrief,
    CampaignProposal,
    LaunchStatus,
)
from adcopilot.domain.launch.templates import build_proposal_from_template
from adcopilot.infrastructure.llm.campaign_generator import (
    AdGroupCopyResponse,
    AdGroupItem,
    BrandCampaignResponse,
    CampaignGenerator,
    KeywordItem,
    VerticalClassification,
)

logger = structlog.get_logger(__name__)


def _apply_seasonal_multiplier(
    proposal: CampaignProposal,
    vertical: str,
) -> tuple[CampaignProposal, float]:
    """Adjust proposal's daily_budget_micros by the Polish market seasonal multiplier.

    Returns (updated_proposal, multiplier). Defaults to 1.0 on any error.
    """
    try:
        from adcopilot.domain.polish_market.seasonality import get_seasonal_multiplier

        month = datetime.now(tz=UTC).month
        multiplier = get_seasonal_multiplier(vertical, month)
    except Exception:
        return proposal, 1.0

    if multiplier == 1.0:
        return proposal, 1.0

    adjusted_budget = int(proposal.daily_budget_micros * multiplier)
    updated = dataclasses.replace(
        proposal,
        daily_budget_micros=adjusted_budget,
        seasonal_multiplier=multiplier,
        seasonal_vertical=vertical,
    )
    return updated, multiplier


def _run_compliance_validators(
    proposal: CampaignProposal,
    vertical: str,
) -> CampaignProposal:
    """Run Polish advertising compliance validators and attach warnings to proposal."""
    try:
        from adcopilot.domain.polish_market.compliance_validators import validate_ad_copy

        all_headlines: list[str] = []
        all_descriptions: list[str] = []
        for ag in proposal.ad_groups:
            for ad in ag.ads:
                all_headlines.extend(ad.headlines)
                all_descriptions.extend(ad.descriptions)
        warnings = validate_ad_copy(all_headlines, all_descriptions, vertical)
        if warnings:
            serialised = [
                {"severity": w.severity, "message": w.message, "suggestion": w.suggestion}
                for w in warnings
            ]
            return dataclasses.replace(proposal, compliance_warnings=serialised)
    except Exception:
        pass
    return proposal


def _apply_purchasing_power(
    proposal: CampaignProposal,
    location: str,
) -> CampaignProposal:
    """Scale proposal's daily_budget_micros by the voivodeship purchasing power index."""
    try:
        from adcopilot.domain.polish_market.voivodeship_data import get_purchasing_power_for_city

        index = get_purchasing_power_for_city(location)
    except Exception:
        return proposal

    if index == 1.0:
        return proposal

    adjusted = int(proposal.daily_budget_micros * index)
    return dataclasses.replace(proposal, daily_budget_micros=adjusted)


class GenerateCampaignProposalUseCase:
    """Orchestrate the full proposal-generation pipeline for a ``CampaignBrief``.

    Constructor arguments
    ---------------------
    brief_repo
        Repository for reading/updating ``CampaignBrief`` status.
    proposal_repo
        Repository for persisting the generated ``CampaignProposal``.
    generator
        ``CampaignGenerator`` adapter wrapping the LLM client.
    website_url
        Optional URL of the advertiser's website (from the Google Ads account).
        Passed to vertical detection for richer classification.
    template_repo
        Optional :class:`VerticalTemplateRepository` for the hybrid path.
        Required when callers pass ``template_id`` to :meth:`execute`.
    assembler
        Optional :class:`TemplateProposalAssembler` for the hybrid path.
        Defaults to a new instance when not provided.
    """

    def __init__(
        self,
        brief_repo: CampaignBriefRepo,
        proposal_repo: CampaignProposalRepo,
        generator: CampaignGenerator,
        website_url: str | None = None,
        template_repo: VerticalTemplateRepository | None = None,
        assembler: TemplateProposalAssembler | None = None,
        keyword_planner: "KeywordPlannerPort | None" = None,
        account_refresh_token: str | None = None,
        account_customer_id: str | None = None,
        competitors: list | None = None,
    ) -> None:
        self._brief_repo = brief_repo
        self._proposal_repo = proposal_repo
        self._generator = generator
        self._website_url = website_url
        self._template_repo = template_repo
        self._assembler = assembler or TemplateProposalAssembler()
        # Optional Keyword Planner: when wired (with account creds) the pipeline
        # enriches structure keywords with real search volume. Absent/failing →
        # the pipeline keeps its template/LLM keywords unchanged (fail-open).
        self._keyword_planner = keyword_planner
        self._account_refresh_token = account_refresh_token
        self._account_customer_id = account_customer_id
        # Top competitors (from auction insights) fetched upstream; fed into the
        # LLM structure prompt so it picks differentiated keywords. Empty/None →
        # no competitor context (new accounts, no auction-insights history).
        self._competitors = competitors or []

    async def execute(
        self,
        brief: CampaignBrief,
        revision_feedback: str | None = None,
        template_id: str | None = None,
    ) -> CampaignProposal:
        """Generate, persist, and return a ``CampaignProposal`` for *brief*.

        Status transitions:
          COLLECTING → GENERATING → PROPOSED   (success path)
          COLLECTING → GENERATING → PROPOSED   (hybrid template path)
          COLLECTING → GENERATING → PROPOSED   (template fallback path)

        Parameters
        ----------
        brief
            The campaign brief to generate a proposal for.
        revision_feedback
            Optional free-text feedback from the user requesting changes to a
            previously generated proposal.  When provided it is passed as LLM
            feedback to the structure and ad-copy stages so the model adjusts
            the output accordingly.
        template_id
            Optional vertical template ID (e.g. ``'beauty_salon'``).  When
            provided *and* the template exists in ``template_repo``, the use
            case skips LLM stages 1 and 2 (vertical detection + campaign
            structure) and uses :class:`TemplateProposalAssembler` instead.
            LLM stages 3 (ad copy) and 4 (negatives) still run.
            Falls back to the full LLM pipeline when ``template_id`` is
            ``None`` or the template is not found.

        Raises
        ------
        ValueError
            If *brief* is not in COLLECTING or GENERATING status.
        """
        if brief.status not in (LaunchStatus.COLLECTING, LaunchStatus.GENERATING):
            raise ValueError(
                f"Cannot generate proposal for brief {brief.id} in status {brief.status!r}"
            )

        await self._brief_repo.update_status(brief.id, LaunchStatus.GENERATING)
        logger.info(
            "proposal_generation_started",
            brief_id=brief.id,
            revision=bool(revision_feedback),
            template_id=template_id,
        )

        # Resolve template for the hybrid path
        resolved_template = None
        if template_id and self._template_repo:
            resolved_template = self._template_repo.get_template(template_id)
            if resolved_template is None:
                logger.warning(
                    "template_not_found_falling_back_to_llm",
                    brief_id=brief.id,
                    template_id=template_id,
                )

        try:
            if resolved_template is not None:
                proposal = await self._run_hybrid_pipeline(
                    brief, resolved_template, revision_feedback=revision_feedback
                )
                logger.info(
                    "proposal_generation_succeeded",
                    brief_id=brief.id,
                    proposal_id=proposal.id,
                    via="hybrid",
                    template_id=template_id,
                )
            else:
                proposal = await self._run_pipeline(brief, revision_feedback=revision_feedback)
                logger.info(
                    "proposal_generation_succeeded",
                    brief_id=brief.id,
                    proposal_id=proposal.id,
                    via="llm",
                )
        except LLMError as exc:
            logger.warning(
                "proposal_generation_failed_using_template",
                brief_id=brief.id,
                error=str(exc)[:300],
            )
            proposal = build_proposal_from_template(brief)
            logger.info(
                "proposal_generation_succeeded",
                brief_id=brief.id,
                proposal_id=proposal.id,
                via="template",
            )

        await self._proposal_repo.save(proposal)
        await self._brief_repo.update_status(brief.id, LaunchStatus.PROPOSED)
        return proposal

    async def generate_content_only(
        self,
        brief: CampaignBrief,
        revision_feedback: str | None = None,
        template_id: str | None = None,
    ) -> CampaignProposal:
        """Run the LLM pipeline and return a proposal **without touching the DB**.

        This method exists so Celery tasks can hold no database connection
        open during the slow LLM calls (avoids idle-in-transaction timeouts on
        managed PostgreSQL).  Callers are responsible for:

        * saving the returned proposal (``proposal_repo.save()``)
        * transitioning the brief status to ``PROPOSED``

        Both operations should happen in a fresh, short-lived transaction
        *after* this method returns.
        """
        logger.info(
            "proposal_generation_started",
            brief_id=brief.id,
            revision=bool(revision_feedback),
            template_id=template_id,
        )

        # Resolve template for the hybrid path
        resolved_template = None
        if template_id and self._template_repo:
            resolved_template = self._template_repo.get_template(template_id)
            if resolved_template is None:
                logger.warning(
                    "template_not_found_falling_back_to_llm",
                    brief_id=brief.id,
                    template_id=template_id,
                )

        try:
            if resolved_template is not None:
                proposal = await self._run_hybrid_pipeline(
                    brief, resolved_template, revision_feedback=revision_feedback
                )
                logger.info(
                    "proposal_generation_succeeded",
                    brief_id=brief.id,
                    proposal_id=proposal.id,
                    via="hybrid",
                    template_id=template_id,
                )
            else:
                proposal = await self._run_pipeline(brief, revision_feedback=revision_feedback)
                logger.info(
                    "proposal_generation_succeeded",
                    brief_id=brief.id,
                    proposal_id=proposal.id,
                    via="llm",
                )
        except LLMError as exc:
            logger.warning(
                "proposal_generation_failed_using_template",
                brief_id=brief.id,
                error=str(exc)[:300],
            )
            proposal = build_proposal_from_template(brief)
            logger.info(
                "proposal_generation_succeeded",
                brief_id=brief.id,
                proposal_id=proposal.id,
                via="template",
            )

        return proposal

    # ------------------------------------------------------------------
    # Hybrid pipeline (template structure + LLM ad copy)
    # ------------------------------------------------------------------

    async def _run_hybrid_pipeline(
        self,
        brief: CampaignBrief,
        template,  # VerticalTemplate — imported lazily to avoid circular deps
        revision_feedback: str | None = None,
    ) -> CampaignProposal:
        """Build proposal from template structure, then personalise ad copy with LLM.

        Stages 1 (vertical detection) and 2 (campaign structure) are replaced by
        the template assembler.  Stages 3 (ad copy) and 4 (negatives) still run.
        """
        import dataclasses as _dc

        # Build template-based proposal (stages 1+2 replaced)
        base_proposal = self._assembler.assemble(template, brief)

        # Synthetic VerticalClassification for stage 4
        vertical = VerticalClassification(
            vertical=template.vertical_id,
            competitive_level=template.competitive_level.value,
            language_hint=template.language,
        )

        # Stage 3 — LLM ad copy for each ad group
        ad_groups_with_llm_copy: list[AdGroupProposal] = []
        for ag in base_proposal.ad_groups:
            # Build a lightweight AdGroupItem for the LLM prompt
            ag_item = AdGroupItem(
                name=ag.name,
                theme=ag.name,
                keywords=[
                    KeywordItem(text=kw.text, match_type=kw.match_type.value)
                    for kw in ag.keywords[:10]
                ],
            )
            try:
                copy_resp: AdGroupCopyResponse = await self._generator.generate_ad_copy(
                    ag_item, brief, feedback=revision_feedback
                )
                ads: list[AdProposal] = [
                    AdProposal(
                        # Clamp to Google Ads hard limits (same as assemble_proposal)
                        headlines=[h[:30] for h in v.headlines],
                        descriptions=[d[:90] for d in v.descriptions],
                        final_url=ag.ads[0].final_url if ag.ads else "https://example.com",
                        path_segments=(v.path1[:15], v.path2[:15]),
                    )
                    for v in copy_resp.variants
                ]
            except LLMError:
                logger.warning(
                    "hybrid_ad_copy_failed_keeping_placeholder",
                    ad_group=ag.name,
                    brief_id=brief.id,
                )
                ads = ag.ads  # keep assembler placeholders

            ad_groups_with_llm_copy.append(
                AdGroupProposal(name=ag.name, keywords=ag.keywords, ads=ads)
            )

        # Stage 4 — LLM negatives (merged with template negatives)
        try:
            neg_resp = await self._generator.generate_negatives(brief, vertical)
            extra_negatives = [
                n for n in neg_resp.keywords if n not in base_proposal.negative_keywords
            ]
        except LLMError:
            logger.warning("hybrid_negatives_failed_using_template_only", brief_id=brief.id)
            extra_negatives = []

        proposal = _dc.replace(
            base_proposal,
            ad_groups=ad_groups_with_llm_copy,
            negative_keywords=base_proposal.negative_keywords + extra_negatives,
        )

        # Apply post-processing (seasonal + purchasing power + compliance)
        proposal, _ = _apply_seasonal_multiplier(proposal, template.vertical_id)
        proposal = _apply_purchasing_power(proposal, brief.location)
        proposal = _run_compliance_validators(proposal, template.vertical_id)

        return proposal

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    async def _maybe_enrich_keywords(self, structure, brief: CampaignBrief) -> None:
        """Attach real Keyword Planner demand to ``structure`` keywords in place.

        Fail-open: returns silently when no planner/credentials are configured or
        on any planner error — the structure keeps its template/LLM keywords.
        """
        if (
            self._keyword_planner is None
            or not self._account_refresh_token
            or not self._account_customer_id
        ):
            return

        from adcopilot.application.services.keyword_enrichment import enrich_keywords

        try:
            seeds: list[str] = []
            for ag in structure.ad_groups:
                seeds.extend(kw.text for kw in ag.keywords)

            ideas = await self._keyword_planner.keyword_ideas(
                self._account_refresh_token,
                self._account_customer_id,
                seed_keywords=seeds,
                seed_url=self._website_url,
                location=brief.location,
            )
            if not ideas:
                return

            total_before = 0
            total_after = 0
            for ag in structure.ad_groups:
                total_before += len(ag.keywords)
                ag.keywords = enrich_keywords(ag.keywords, ideas)
                total_after += len(ag.keywords)

            logger.info(
                "keywords_enriched_with_demand",
                brief_id=brief.id,
                ideas=len(ideas),
                keywords_before=total_before,
                keywords_after=total_after,
            )
        except Exception:
            logger.warning("keyword_enrichment_failed", brief_id=brief.id)

    async def _run_pipeline(
        self,
        brief: CampaignBrief,
        revision_feedback: str | None = None,
    ) -> CampaignProposal:
        """Run all four LLM stages; validate; retry once; raise on second failure."""
        # Stage 1 — vertical detection
        vertical = await self._generator.detect_vertical(
            brief.business_description, self._website_url
        )
        logger.debug("vertical_detected", vertical=vertical.vertical, brief_id=brief.id)

        # Stage 2 — campaign structure (pass revision feedback + competitor scan)
        structure = await self._generator.build_structure(
            brief, vertical, feedback=revision_feedback, competitors=self._competitors
        )

        # Stage 2a — enrich structure keywords with real Keyword Planner demand
        # (fail-open: no-op when no planner/creds, or on any API error).
        await self._maybe_enrich_keywords(structure, brief)

        # Stage 3 — ad copy (one call per ad group, sequential)
        ad_copies = []
        for ag in structure.ad_groups:
            copy = await self._generator.generate_ad_copy(ag, brief, feedback=revision_feedback)
            ad_copies.append(copy)

        # Stage 4 — negative keywords
        negatives = await self._generator.generate_negatives(brief, vertical)

        # Stage 5 — extensions (sitelinks, callouts, structured snippets)
        try:
            extensions = await self._generator.generate_extensions(brief, vertical)
        except Exception:
            extensions = None
            logger.warning("extensions_generation_failed", brief_id=brief.id)

        # Stage 2b — brand campaign (MID/GROWTH only)
        brand: BrandCampaignResponse | None = None
        _tier = classify_budget_tier(brief.monthly_budget_pln)
        if _tier in (BudgetTier.MID, BudgetTier.GROWTH):
            try:
                brand = await self._generator.generate_brand_campaign(
                    brief, structure.campaign_name
                )
            except Exception:
                brand = None
                logger.warning("brand_campaign_generation_failed", brief_id=brief.id)

        # Assemble
        proposal = self._generator.assemble_proposal(
            brief, structure, ad_copies, negatives, extensions, brand
        )

        # Apply seasonal multiplier to daily budget
        proposal, seasonal_multiplier = _apply_seasonal_multiplier(proposal, vertical.vertical)
        if seasonal_multiplier != 1.0:
            logger.info(
                "seasonal_multiplier_applied",
                brief_id=brief.id,
                vertical=vertical.vertical,
                month=datetime.now(tz=UTC).month,
                multiplier=seasonal_multiplier,
            )

        # Apply voivodeship purchasing power adjustment
        proposal = _apply_purchasing_power(proposal, brief.location)

        # Run Polish advertising compliance validators
        proposal = _run_compliance_validators(proposal, vertical.vertical)

        # Build validation context with landing page check
        lp_ctx = await self._build_validation_context(proposal)
        errors_result = validate_proposal(proposal, brief, lp_ctx)
        errors = errors_result.errors

        if not errors:
            return proposal

        # Validation retry — rebuild ad copy (covers most errors) and
        # optionally the structure (covers keyword-count errors)
        logger.warning(
            "proposal_validation_failed_retrying",
            brief_id=brief.id,
            error_count=len(errors),
        )
        validation_feedback = "\n".join(f"- {e}" for e in errors)
        # Merge revision feedback into the validation feedback if both exist
        combined_feedback = (
            f"{revision_feedback}\n\nValidation issues to fix:\n{validation_feedback}"
            if revision_feedback
            else validation_feedback
        )

        has_copy_errors = any("headline" in e or "description" in e or "path" in e for e in errors)
        has_structure_errors = any("keyword" in e for e in errors)

        if has_structure_errors:
            structure = await self._generator.build_structure(
                brief, vertical, feedback=combined_feedback, competitors=self._competitors
            )

        if has_copy_errors or has_structure_errors:
            ad_copies = []
            for ag in structure.ad_groups:
                copy = await self._generator.generate_ad_copy(
                    ag, brief, feedback=combined_feedback if has_copy_errors else None
                )
                ad_copies.append(copy)

        proposal = self._generator.assemble_proposal(
            brief, structure, ad_copies, negatives, extensions
        )
        proposal, _ = _apply_seasonal_multiplier(proposal, vertical.vertical)
        proposal = _apply_purchasing_power(proposal, brief.location)
        proposal = _run_compliance_validators(proposal, vertical.vertical)
        errors2_result = validate_proposal(proposal, brief, lp_ctx)
        errors2 = errors2_result.errors

        if errors2:
            raise LLMError(
                f"Proposal still invalid after retry ({len(errors2)} errors): "
                + "; ".join(errors2[:3])
            )

        return proposal

    async def _build_validation_context(self, proposal: CampaignProposal) -> ValidationContext:
        """Probe landing page URLs and build a ValidationContext with the results."""
        from adcopilot.infrastructure.landing_page.checker import LandingPageChecker
        from adcopilot.infrastructure.landing_page.checker import (
            LandingPageCheckResult as InfraLPResult,
        )

        urls: set[str] = set()
        for ag in proposal.ad_groups:
            for ad in ag.ads:
                if ad.final_url:
                    urls.add(ad.final_url)

        lp_results: dict[str, DetectionLPResult] = {}
        checker = LandingPageChecker()
        for url in urls:
            try:
                infra_result: InfraLPResult = await checker.check(url)
                lp_results[url] = DetectionLPResult(
                    url=url,
                    reachable=infra_result.reachable,
                    https=infra_result.https,
                    load_time_seconds=infra_result.load_time_seconds,
                    language_detected=infra_result.language_detected,
                    error_message=infra_result.error_message,
                    page_title=infra_result.page_title,
                    h1_text=infra_result.h1_text,
                    body_text_sample=infra_result.body_text_sample,
                )
            except Exception:
                logger.warning("landing_page_check_failed_skipping", url=url)

        return ValidationContext(landing_page_results=lp_results)
