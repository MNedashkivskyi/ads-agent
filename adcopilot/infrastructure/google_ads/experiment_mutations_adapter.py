"""Native Google Ads campaign-experiment adapter (causal measurement).

Implements ExperimentMutationsPort against CampaignDraftService /
ExperimentService / GoogleAdsService. Experiments have no validate_only and run
for weeks, so proto construction here is validated live on a real account; the
pure metrics parser (`_parse_metrics`) is unit-tested.
"""

from __future__ import annotations

from typing import Any

import structlog

from adcopilot.application.ports.experiment_mutations import (
    DraftHandle,
    ExperimentMetrics,
)
from adcopilot.config import Settings
from adcopilot.domain.exceptions import (
    GoogleAdsAuthError,
    GoogleAdsRateLimited,
    GoogleAdsUnavailable,
)
from adcopilot.infrastructure.google_ads.client import (
    GoogleAdsClientAdapter,
    is_google_auth_error,
    is_rate_limit_error,
)
from adcopilot.infrastructure.google_ads.resilience import throttled_adapter

logger = structlog.get_logger(__name__)


def _wrap(op: str, exc: Exception) -> Exception:
    if is_google_auth_error(exc):
        return GoogleAdsAuthError(str(exc))
    if is_rate_limit_error(exc):
        return GoogleAdsRateLimited(f"{op} rate-limited: {exc}")
    return GoogleAdsUnavailable(f"{op} failed: {exc}")


def _metrics_from_row(row: Any) -> dict:
    m = row.metrics
    return {
        "impressions": int(getattr(m, "impressions", 0) or 0),
        "clicks": int(getattr(m, "clicks", 0) or 0),
        "cost_micros": int(getattr(m, "cost_micros", 0) or 0),
        "conversions": float(getattr(m, "conversions", 0.0) or 0.0),
        "conversions_value": float(getattr(m, "conversions_value", 0.0) or 0.0),
    }


def _parse_metrics(
    rows: list, control_campaign_id: int, treatment_campaign_id: int
) -> ExperimentMetrics:
    """Pure: split per-campaign metric rows into control vs treatment arms."""
    control: dict = {}
    treatment: dict = {}
    for row in rows:
        cid = int(row.campaign.id)
        if cid == control_campaign_id:
            control = _metrics_from_row(row)
        elif cid == treatment_campaign_id:
            treatment = _metrics_from_row(row)
    return ExperimentMetrics(status="RUNNING", control=control, treatment=treatment)


@throttled_adapter
class GoogleAdsExperimentAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = GoogleAdsClientAdapter(settings)

    def _build_client(self, refresh_token: str) -> Any:
        return self._client._build_client(refresh_token)

    async def create_campaign_draft(
        self, refresh_token: str, customer_id: str, base_campaign_id: int, name: str
    ) -> DraftHandle:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            draft_service = client.get_service("CampaignDraftService")
            campaign_service = client.get_service("CampaignService")
            op = client.get_type("CampaignDraftOperation")
            draft = op.create
            draft.base_campaign = campaign_service.campaign_path(cid, base_campaign_id)
            draft.name = name
            resp = draft_service.mutate_campaign_drafts(customer_id=cid, operations=[op])
            draft_rn = resp.results[0].resource_name
            # draft resource: customers/{cid}/campaignDrafts/{base}~{draftId}
            draft_campaign_id = int(draft_rn.split("~")[-1])
            logger.info("campaign_draft_created", customer_id=customer_id, draft=draft_rn)
            return DraftHandle(draft_resource_name=draft_rn, draft_campaign_id=draft_campaign_id)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:  # noqa: BLE001
            raise _wrap("create_campaign_draft", exc) from exc

    async def apply_bidding_change_to_draft(
        self,
        refresh_token: str,
        customer_id: str,
        draft_campaign_id: int,
        change_kind: str,
        change_payload: dict,
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            campaign_service = client.get_service("CampaignService")
            op = client.get_type("CampaignOperation")
            campaign = op.update
            campaign.resource_name = campaign_service.campaign_path(cid, draft_campaign_id)
            from google.protobuf import field_mask_pb2

            paths: list[str] = []
            if change_kind == "TARGET_CPA":
                campaign.target_cpa.target_cpa_micros = int(change_payload["target_cpa_micros"])
                paths.append("target_cpa.target_cpa_micros")
            elif change_kind == "TARGET_ROAS":
                campaign.target_roas.target_roas = float(change_payload["target_roas"])
                paths.append("target_roas.target_roas")
            elif change_kind == "BIDDING_STRATEGY":
                strat = change_payload["bidding_strategy"].upper()
                campaign.bidding_strategy_type = client.enums.BiddingStrategyTypeEnum[strat]
                paths.append("bidding_strategy_type")
            client.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=paths))
            campaign_service.mutate_campaigns(customer_id=cid, operations=[op])
            logger.info("draft_bidding_change_applied", customer_id=customer_id, kind=change_kind)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:  # noqa: BLE001
            raise _wrap("apply_bidding_change_to_draft", exc) from exc

    async def create_and_schedule_experiment(
        self,
        refresh_token: str,
        customer_id: str,
        base_campaign_id: int,
        draft: DraftHandle,
        traffic_split: int,
        name: str,
        days: int,
    ) -> str:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            campaign_service = client.get_service("CampaignService")
            exp_service = client.get_service("ExperimentService")
            arm_service = client.get_service("ExperimentArmService")

            # 1) create the experiment shell
            exp_op = client.get_type("ExperimentOperation")
            exp = exp_op.create
            exp.name = name
            exp.type_ = client.enums.ExperimentTypeEnum.SEARCH_CUSTOM
            exp.status = client.enums.ExperimentStatusEnum.SETUP
            exp_rn = exp_service.mutate_experiments(
                customer_id=cid, operations=[exp_op]
            ).results[0].resource_name

            # 2) control arm (base campaign) + treatment arm (traffic split)
            control_op = client.get_type("ExperimentArmOperation")
            control = control_op.create
            control.experiment = exp_rn
            control.name = "control"
            control.control = True
            control.campaigns.append(campaign_service.campaign_path(cid, base_campaign_id))

            treat_op = client.get_type("ExperimentArmOperation")
            treat = treat_op.create
            treat.experiment = exp_rn
            treat.name = "treatment"
            treat.control = False
            treat.traffic_split = int(traffic_split)
            arm_service.mutate_experiment_arms(customer_id=cid, operations=[control_op, treat_op])

            # 3) schedule (starts the experiment running)
            exp_service.schedule_experiment(resource_name=exp_rn)
            logger.info("experiment_scheduled", customer_id=customer_id, experiment=exp_rn)
            return exp_rn
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:  # noqa: BLE001
            raise _wrap("create_and_schedule_experiment", exc) from exc

    async def get_experiment_metrics(
        self, refresh_token: str, customer_id: str, experiment_resource_name: str
    ) -> ExperimentMetrics:
        """Read per-arm campaign metrics for a running/finished experiment.

        Resolves the control + treatment campaign IDs from the experiment's arms
        at read time (Google materialises the treatment campaign asynchronously
        after scheduling, so there is nothing reliable to persist up front), then
        queries aggregated metrics for both and splits them via ``_parse_metrics``.
        Returns empty arms with status ``PENDING`` until both campaigns exist.
        """
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            ga = client.get_service("GoogleAdsService")

            # 1) Resolve arm → campaign IDs. control flag distinguishes the arms;
            #    `campaigns` holds the live (post-schedule) campaign resource names.
            arm_query = (
                "SELECT experiment_arm.control, experiment_arm.campaigns "
                "FROM experiment_arm "
                f"WHERE experiment_arm.experiment = '{experiment_resource_name}'"
            )
            control_id: int | None = None
            treatment_id: int | None = None
            for row in ga.search(customer_id=cid, query=arm_query):
                arm = row.experiment_arm
                campaign_ids = [int(rn.rsplit("/", 1)[-1]) for rn in arm.campaigns]
                if not campaign_ids:
                    continue
                if arm.control:
                    control_id = campaign_ids[0]
                else:
                    treatment_id = campaign_ids[0]

            if control_id is None or treatment_id is None:
                # Experiment still spinning up — arms/campaigns not materialised.
                return ExperimentMetrics(status="PENDING", control={}, treatment={})

            # 2) Aggregated metrics per arm campaign (no segments.date in SELECT →
            #    the date filter aggregates over the window into one row/campaign).
            metrics_query = (
                "SELECT campaign.id, metrics.impressions, metrics.clicks, "
                "metrics.cost_micros, metrics.conversions, metrics.conversions_value "
                "FROM campaign "
                f"WHERE campaign.id IN ({control_id}, {treatment_id}) "
                "AND segments.date DURING LAST_30_DAYS"
            )
            rows = list(ga.search(customer_id=cid, query=metrics_query))
            return _parse_metrics(rows, control_id, treatment_id)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:  # noqa: BLE001
            raise _wrap("get_experiment_metrics", exc) from exc

    async def promote_experiment(
        self, refresh_token: str, customer_id: str, experiment_resource_name: str
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            client.get_service("ExperimentService").promote_experiment(
                resource_name=experiment_resource_name
            )
            logger.info("experiment_promoted", customer_id=customer_id, experiment=experiment_resource_name)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:  # noqa: BLE001
            raise _wrap("promote_experiment", exc) from exc

    async def end_experiment(
        self, refresh_token: str, customer_id: str, experiment_resource_name: str
    ) -> None:
        try:
            client = self._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            client.get_service("ExperimentService").end_experiment(
                experiment=experiment_resource_name
            )
            logger.info("experiment_ended", customer_id=customer_id, experiment=experiment_resource_name)
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:  # noqa: BLE001
            raise _wrap("end_experiment", exc) from exc
