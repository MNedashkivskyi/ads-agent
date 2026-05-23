"""Use case: request GTM installation from an implementation partner."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.implementation_partner import (
    ImplementationRequest,
    ImplementationRequestId,
    ImplementationRequestStatus,
)
from adcopilot.infrastructure.db.models import (
    ImplementationPartnerModel,
    ImplementationRequestModel,
)

logger = structlog.get_logger(__name__)


async def request_implementation(
    user_id: str,
    account_id: str,
    platform: str,
    session: AsyncSession,
    partner_id: str | None = None,
) -> ImplementationRequest:
    """Create an implementation request, auto-matching partner by platform if none provided."""
    if partner_id:
        partner = await session.get(ImplementationPartnerModel, uuid.UUID(partner_id))
        if partner is None:
            raise ValueError(f"Partner {partner_id} not found")
    else:
        partner = await _auto_match_partner(platform, session)
        if partner is None:
            raise ValueError(f"No active partner found for platform '{platform}'")

    now = datetime.now(UTC)
    request = ImplementationRequest(
        id=ImplementationRequestId(str(uuid.uuid4())),
        client_id=user_id,
        partner_id=str(partner.id),
        account_id=account_id,
        status=ImplementationRequestStatus.REQUESTED,
        platform=platform,
        created_at=now,
        accepted_at=None,
        completed_at=None,
        cancelled_at=None,
    )

    row = ImplementationRequestModel(
        id=uuid.UUID(request.id),
        client_id=request.client_id,
        partner_id=uuid.UUID(request.partner_id),
        account_id=uuid.UUID(request.account_id),
        status=request.status.value,
        platform=request.platform,
        created_at=request.created_at,
    )
    session.add(row)
    await session.flush()

    await _notify_partner(partner, request, platform)
    await _notify_client_telegram(user_id, partner, platform)

    logger.info(
        "implementation_request_created",
        request_id=request.id,
        partner_id=str(partner.id),
        platform=platform,
    )
    return request


async def _auto_match_partner(platform: str, session: AsyncSession) -> ImplementationPartnerModel | None:
    result = await session.execute(
        select(ImplementationPartnerModel)
        .where(ImplementationPartnerModel.is_active == True)  # noqa: E712
        .order_by(ImplementationPartnerModel.rating.desc())
    )
    partners = list(result.scalars().all())
    for p in partners:
        platforms = p.platforms_supported or []
        if platform in platforms:
            return p
    return partners[0] if partners else None


async def _notify_partner(
    partner: ImplementationPartnerModel,
    request: ImplementationRequest,
    platform: str,
) -> None:
    try:
        import httpx

        from adcopilot.config import get_settings
        settings = get_settings()
        if not getattr(settings, "SENDGRID_API_KEY", None):
            logger.info("email_skipped_no_sendgrid", partner_email=partner.email)
            return

        body = (
            f"Nowe zlecenie instalacji GTM\n\n"
            f"Klient ID: {request.client_id}\n"
            f"Platforma: {platform}\n"
            f"ID zlecenia: {request.id}\n\n"
            f"Proszę skontaktować się z klientem w celu ustalenia szczegółów."
        )
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"},
                json={
                    "personalizations": [{"to": [{"email": partner.email}]}],
                    "from": {"email": "noreply@adswise.pl"},
                    "subject": f"Nowe zlecenie GTM — {platform}",
                    "content": [{"type": "text/plain", "value": body}],
                },
                timeout=10,
            )
    except Exception as exc:
        logger.warning("partner_email_failed", partner_id=str(partner.id), error=str(exc))


async def _notify_client_telegram(
    user_id: str,
    partner: ImplementationPartnerModel,
    platform: str,
) -> None:
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from adcopilot.config import get_settings
        from adcopilot.infrastructure.db.models import UserModel

        settings = get_settings()
        engine = create_async_engine(settings.DATABASE_URL)
        try:
            async with AsyncSession(engine) as s:
                user = await s.get(UserModel, uuid.UUID(user_id) if _is_uuid(user_id) else None)
                if user and user.telegram_chat_id:
                    import httpx
                    msg = (
                        f"✅ Zlecenie instalacji GTM wysłane!\n\n"
                        f"Partner: {partner.name}\n"
                        f"Platforma: {platform}\n"
                        f"Cena: {partner.fixed_price_pln} PLN\n"
                        f"Czas realizacji: do {partner.avg_turnaround_hours}h\n\n"
                        f"Partner skontaktuje się z Tobą wkrótce."
                    )
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                            json={"chat_id": user.telegram_chat_id, "text": msg},
                            timeout=10,
                        )
        finally:
            await engine.dispose()
    except Exception as exc:
        logger.warning("client_telegram_notification_failed", user_id=user_id, error=str(exc))


def _is_uuid(val: str) -> bool:
    try:
        uuid.UUID(val)
        return True
    except ValueError:
        return False
