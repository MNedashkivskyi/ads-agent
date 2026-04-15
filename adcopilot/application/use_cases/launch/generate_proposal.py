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

import structlog

from adcopilot.application.ports.launch_repositories import (
    CampaignBriefRepo,
    CampaignProposalRepo,
)
from adcopilot.domain.exceptions import LLMError
from adcopilot.domain.launch.entities import CampaignBrief, CampaignProposal, LaunchStatus
from adcopilot.domain.launch.templates import build_proposal_from_template
from adcopilot.domain.launch.validator import validate_proposal
from adcopilot.infrastructure.llm.campaign_generator import CampaignGenerator

logger = structlog.get_logger(__name__)


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
    """

    def __init__(
        self,
        brief_repo: CampaignBriefRepo,
        proposal_repo: CampaignProposalRepo,
        generator: CampaignGenerator,
        website_url: str | None = None,
    ) -> None:
        self._brief_repo = brief_repo
        self._proposal_repo = proposal_repo
        self._generator = generator
        self._website_url = website_url

    async def execute(
        self,
        brief: CampaignBrief,
        revision_feedback: str | None = None,
    ) -> CampaignProposal:
        """Generate, persist, and return a ``CampaignProposal`` for *brief*.

        Status transitions:
          COLLECTING → GENERATING → PROPOSED   (success path)
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

        Raises
        ------
        ValueError
            If *brief* is not in COLLECTING or GENERATING status.
        """
        if brief.status not in (LaunchStatus.COLLECTING, LaunchStatus.GENERATING):
            raise ValueError(
                f"Cannot generate proposal for brief {brief.id} "
                f"in status {brief.status!r}"
            )

        await self._brief_repo.update_status(brief.id, LaunchStatus.GENERATING)
        logger.info(
            "proposal_generation_started",
            brief_id=brief.id,
            revision=bool(revision_feedback),
        )

        try:
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

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

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

        # Stage 2 — campaign structure (pass revision feedback when provided)
        structure = await self._generator.build_structure(
            brief, vertical, feedback=revision_feedback
        )

        # Stage 3 — ad copy (one call per ad group, sequential)
        ad_copies = []
        for ag in structure.ad_groups:
            copy = await self._generator.generate_ad_copy(
                ag, brief, feedback=revision_feedback
            )
            ad_copies.append(copy)

        # Stage 4 — negative keywords
        negatives = await self._generator.generate_negatives(brief, vertical)

        # Assemble and validate
        proposal = self._generator.assemble_proposal(brief, structure, ad_copies, negatives)
        errors = validate_proposal(proposal, brief)

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

        has_copy_errors = any(
            "headline" in e or "description" in e or "path" in e
            for e in errors
        )
        has_structure_errors = any("keyword" in e for e in errors)

        if has_structure_errors:
            structure = await self._generator.build_structure(
                brief, vertical, feedback=combined_feedback
            )

        if has_copy_errors or has_structure_errors:
            ad_copies = []
            for ag in structure.ad_groups:
                copy = await self._generator.generate_ad_copy(
                    ag, brief, feedback=combined_feedback if has_copy_errors else None
                )
                ad_copies.append(copy)

        proposal = self._generator.assemble_proposal(brief, structure, ad_copies, negatives)
        errors2 = validate_proposal(proposal, brief)

        if errors2:
            raise LLMError(
                f"Proposal still invalid after retry ({len(errors2)} errors): "
                + "; ".join(errors2[:3])
            )

        return proposal
