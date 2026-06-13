"""DbCreativeFlowService — production wiring for the creative (hook) API."""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import Settings
from adcopilot.domain.campaign_intelligence.creatives.hook_run import HookRun, HookRunStatus
from adcopilot.infrastructure.cie.campaign_context import (
    CampaignForbidden,
    CampaignNotFound,
    resolve_campaign_context,
)
from adcopilot.infrastructure.db.repositories.cie_hook_repository import SqlCieHookRepository

logger = structlog.get_logger(__name__)

__all__ = ["CampaignForbidden", "CampaignNotFound", "DbCreativeFlowService"]


class DbCreativeFlowService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _engine(self):  # noqa: ANN202
        return create_async_engine(self._settings.DATABASE_URL)

    async def generate(
        self,
        *,
        campaign_id: str,
        user_id: str,
        account_id: str | None = None,
        vertical: str | None = None,
        language: str | None = None,
        service: str | None = None,
        problems: list[str] | None = None,
    ) -> str:
        engine = self._engine()
        try:
            async with AsyncSession(engine) as session, session.begin():
                ctx = await resolve_campaign_context(
                    session,
                    campaign_id=campaign_id,
                    user_id=user_id,
                    account_id=account_id,
                    vertical=vertical,
                    language=language,
                    service=service,
                )
                run = HookRun(
                    campaign_id=campaign_id,
                    account_id=ctx.account_id,
                    user_id=user_id,
                    vertical=ctx.vertical,
                    language=ctx.language,
                    service=ctx.service,
                    problems=problems or [],
                    status=HookRunStatus.GENERATING,
                )
                run_id = await SqlCieHookRepository(session).create_run(run)
        finally:
            await engine.dispose()

        from adcopilot.interfaces.worker.cie_tasks import cie_generate_hooks_task

        cie_generate_hooks_task.delay(run_id)
        logger.info("cie.hooks.generate.dispatched", run_id=run_id, campaign_id=campaign_id)
        return run_id

    async def select(self, *, campaign_id: str, user_id: str) -> str:
        run_id = await self._latest_run_id(campaign_id, user_id)

        from adcopilot.interfaces.worker.cie_tasks import cie_select_hooks_task

        cie_select_hooks_task.delay(run_id)
        return run_id

    async def finalize(self, *, campaign_id: str, user_id: str) -> str:
        run_id = await self._latest_run_id(campaign_id, user_id)

        from adcopilot.interfaces.worker.cie_tasks import cie_finalize_hooks_task

        cie_finalize_hooks_task.delay(run_id)
        return run_id

    async def get_status(
        self, *, campaign_id: str, user_id: str
    ) -> tuple[str | None, str | None, dict | None]:
        engine = self._engine()
        try:
            async with AsyncSession(engine) as session:
                run = await SqlCieHookRepository(session).get_latest_run_for_campaign(
                    campaign_id, user_id
                )
                if run is None:
                    return None, None, None
                return run.status.value, run.id, run.rsa_payload
        finally:
            await engine.dispose()

    async def _latest_run_id(self, campaign_id: str, user_id: str) -> str:
        engine = self._engine()
        try:
            async with AsyncSession(engine) as session:
                run = await SqlCieHookRepository(session).get_latest_run_for_campaign(
                    campaign_id, user_id
                )
                if run is None or run.id is None:
                    raise CampaignNotFound("No hook run found — generate first")
                return run.id
        finally:
            await engine.dispose()
