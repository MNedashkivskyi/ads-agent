"""Reusable FastAPI dependencies for capability gating and account limits.

These wrap the pure entitlements logic in ``adcopilot.application.entitlements``
with the framework/DB plumbing needed to enforce it on HTTP routes. Keeping the
FastAPI- and DB-aware code here (rather than in the application layer) preserves
the application layer's independence from the web framework.

Usage:

    from adcopilot.application.entitlements import Capability
    from adcopilot.interfaces.api.deps import require_capability

    @router.post("/{user_id}/something")
    async def something(
        user_id: str,
        current_user: CurrentUser,
        _: None = Depends(require_capability(Capability.AUDIENCES)),
    ) -> ...:
        ...
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import structlog
from fastapi import Depends, HTTPException

from adcopilot.application.entitlements import Capability, has_capability, max_accounts
from adcopilot.config import Settings, get_settings
from adcopilot.domain.entities import PlanTier, UserId
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

# Polish upgrade messages surfaced as the 403 detail. Per-capability so the copy
# can point the user at the right tier; falls back to a generic prompt.
_UPGRADE_MESSAGE: dict[Capability, str] = {
    Capability.MEASUREMENT_LOOP: (
        "Pętla pomiarowa (GA4 + konwersje offline) jest dostępna od planu "
        "Professional. Zaktualizuj swój plan, aby ją włączyć."
    ),
    Capability.AUDIENCES: (
        "Strategie odbiorców są dostępne od planu Professional. "
        "Zaktualizuj swój plan, aby ich używać."
    ),
    Capability.STRUCTURE_SEASONALITY: (
        "Struktura konta i sezonowość są dostępne od planu Professional. "
        "Zaktualizuj swój plan."
    ),
    Capability.AI_INSIGHTS: (
        "Analizy AI są dostępne od planu Professional. Zaktualizuj swój plan."
    ),
    Capability.AB_EXPERIMENTS: (
        "Eksperymenty A/B są dostępne od planu Professional. Zaktualizuj swój plan."
    ),
    Capability.ADVANCED_OPTIMIZATION: (
        "Zaawansowana optymalizacja AI (treści reklam i słowa kluczowe) jest "
        "dostępna od planu Professional. Zaktualizuj swój plan."
    ),
    Capability.AUTO_APPLY: (
        "Tryb automatycznego wdrażania jest dostępny od planu Professional. "
        "Zaktualizuj swój plan."
    ),
    Capability.PMAX_OPTIMIZATION: (
        "Optymalizacja kampanii PMax jest dostępna od planu Professional. "
        "Zaktualizuj swój plan."
    ),
    Capability.CAUSAL_EXPERIMENTS: (
        "Eksperymenty przyczynowe są dostępne w planie Business. "
        "Zaktualizuj swój plan."
    ),
    Capability.CROSS_ACCOUNT_REPORTS: (
        "Raporty wielokontowe i brandowane są dostępne w planie Business. "
        "Zaktualizuj swój plan."
    ),
    Capability.TEAM_SEATS: (
        "Miejsca dla zespołu są dostępne w planie Business. Zaktualizuj swój plan."
    ),
    Capability.API_ACCESS: (
        "Dostęp do API jest dostępny w planie Business. Zaktualizuj swój plan."
    ),
}


def _upgrade_message(capability: Capability) -> str:
    return _UPGRADE_MESSAGE.get(
        capability,
        "Ta funkcja wymaga wyższego planu. Zaktualizuj swój plan, aby ją włączyć.",
    )


async def _load_plan(user_id: str, settings: Settings) -> PlanTier:
    """Load the user's plan tier, defaulting to the most restrictive tier."""
    # Import inside the function (mirroring the rest of this codebase) so test
    # patches on ``sqlalchemy.ext.asyncio`` are resolved at call time.
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.user_repository import (
        SqlUserRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    session = AsyncSession(engine)
    try:
        repo = SqlUserRepository(session)
        user = await repo.get_by_id(UserId(user_id))
    finally:
        await session.close()
        await engine.dispose()
    return user.plan if user is not None else PlanTier.STARTER


def require_capability(
    capability: Capability,
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Build a FastAPI dependency that gates a route by ``capability``.

    The dependency loads the plan of the *authenticated* user (the JWT subject),
    so it works on any route regardless of whether a ``user_id`` path parameter
    is present. It raises HTTP 403 with a Polish upgrade message if the plan is
    not entitled; on success it returns ``None``.
    """

    async def _dependency(
        current_user: CurrentUser,
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> None:
        plan = await _load_plan(current_user, settings)
        if not has_capability(plan, capability):
            logger.info(
                "entitlements.capability_denied",
                user_id=current_user,
                plan=plan.value,
                capability=capability.value,
            )
            raise HTTPException(
                status_code=403,
                detail=_upgrade_message(capability),
            )

    return _dependency


async def require_campaign_creation_enabled(
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Gate a route behind the greenfield campaign-creation kill-switch.

    When ``CAMPAIGN_CREATION_ENABLED`` is False (the default after the
    optimization pivot), the route responds 404 — as if it does not exist —
    so brand-new campaign creation is fully off the API surface. Flipping the
    flag True restores the route. See Phase 1 / T1.1.
    """
    if not settings.CAMPAIGN_CREATION_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")


def assert_within_account_limit(plan: PlanTier, current_count: int) -> None:
    """Guard the OAuth account-link flow against the plan's account limit.

    ``max_accounts`` of ``None`` means unlimited (Business) and is always
    allowed. Raises HTTP 402 with a Polish message when the limit is reached.
    """
    limit = max_accounts(plan)
    if limit is None:
        return
    if current_count >= limit:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Osiągnięto limit kont dla planu {plan.value} "
                f"(maks. {limit}). Zaktualizuj plan, aby dodać kolejne konta."
            ),
        )
