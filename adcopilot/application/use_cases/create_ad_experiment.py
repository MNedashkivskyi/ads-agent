"""CreateAdExperimentUseCase — set up a controlled A/B test for ad creative."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from adcopilot.domain.ad_copy_proposal import AdCopyProposal

logger = structlog.get_logger(__name__)


@dataclass
class ExperimentCreateRequest:
    account_id: str
    customer_id: str
    refresh_token: str
    ad_group_resource_name: str
    campaign_resource_name: str
    control_ad_resource_name: str
    proposal: AdCopyProposal  # the variant ad copy to test
    min_impressions: int = 1000
    confidence_threshold: float = 0.95


@dataclass
class ExperimentCreateResult:
    experiment_id: str
    variant_ad_resource_name: str


class CreateAdExperimentUseCase:
    def __init__(self, mutations_adapter: object, experiment_repo: object) -> None:
        self._mutations = mutations_adapter
        self._repo = experiment_repo

    async def execute(self, req: ExperimentCreateRequest) -> ExperimentCreateResult:
        from adcopilot.infrastructure.google_ads.mutations_adapter import GoogleAdsMutationsAdapter
        from adcopilot.infrastructure.db.repositories.ad_experiment_repository import (
            AdExperimentRepository,
        )

        assert isinstance(self._mutations, GoogleAdsMutationsAdapter)
        assert isinstance(self._repo, AdExperimentRepository)

        # Parse ad group id from resource name
        # Format: customers/{cid}/adGroups/{ad_group_id}
        ad_group_id = int(req.ad_group_resource_name.split("/")[-1])

        # Set control ad to ENABLED (in case it was paused)
        control_ad_id = int(req.control_ad_resource_name.split("~")[-1])
        await self._mutations.enable_ad(
            refresh_token=req.refresh_token,
            customer_id=req.customer_id,
            ad_group_id=ad_group_id,
            ad_id=control_ad_id,
        )

        # Create variant RSA (starts PAUSED, then we enable it)
        variant_ad_id = await self._mutations.create_rsa(
            refresh_token=req.refresh_token,
            customer_id=req.customer_id,
            ad_group_id=ad_group_id,
            headlines=req.proposal.headlines,
            descriptions=req.proposal.descriptions,
            final_url=req.proposal.final_url,
        )

        # Enable variant to run alongside control
        await self._mutations.enable_ad(
            refresh_token=req.refresh_token,
            customer_id=req.customer_id,
            ad_group_id=ad_group_id,
            ad_id=variant_ad_id,
        )

        cid_clean = req.customer_id.replace("-", "")
        variant_resource = f"customers/{cid_clean}/adGroupAds/{ad_group_id}~{variant_ad_id}"

        experiment_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        await self._repo.create(
            experiment_id=experiment_id,
            account_id=req.account_id,
            campaign_resource_name=req.campaign_resource_name,
            ad_group_resource_name=req.ad_group_resource_name,
            control_ad_resource_name=req.control_ad_resource_name,
            variant_ad_resource_name=variant_resource,
            min_impressions=req.min_impressions,
            confidence_threshold=req.confidence_threshold,
            started_at=now,
        )

        logger.info(
            "ad_experiment.created",
            experiment_id=experiment_id,
            account_id=req.account_id,
            control=req.control_ad_resource_name,
            variant=variant_resource,
        )

        return ExperimentCreateResult(
            experiment_id=experiment_id,
            variant_ad_resource_name=variant_resource,
        )
