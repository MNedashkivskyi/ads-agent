"""Manual digest trigger endpoint."""

from datetime import UTC
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adcopilot.config import Settings, get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/users", tags=["digest"])


class DigestResponse(BaseModel):
    sent: bool
    count: int
    reason: str


@router.post("/{user_id}/digest", response_model=DigestResponse, status_code=202)
async def trigger_digest(
    user_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DigestResponse:
    """Manually trigger a daily digest for a user."""
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.send_daily_digest import SendDailyDigestUseCase
    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.infrastructure.db.models import UserModel
    from adcopilot.infrastructure.db.repositories.digest_sent_log_repository import (
        SqlDigestSentLogRepository,
    )
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )

    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")

    from sqlalchemy import select

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            result = await session.execute(
                select(UserModel).where(UserModel.id == _parse_user_uuid(user_id))
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                raise HTTPException(status_code=404, detail="User not found")

            account_repo = SqlGoogleAdsAccountRepository(session)
            rec_repo = SqlRecommendationRepository(session)
            digest_log_repo = SqlDigestSentLogRepository(session)

            accounts = await account_repo.list_for_user(UserId(user_id))
            account_ids = [AccountId(a.id) for a in accounts]

            # TODO(phase-0.2): wire new notifier implementation
            raise HTTPException(status_code=503, detail="Digest notifier not configured")
            use_case = SendDailyDigestUseCase(
                account_repo=account_repo,
                rec_repo=rec_repo,
                digest_log_repo=digest_log_repo,
                notifier=notifier,
            )
            digest_result = await use_case.execute(
                user_id=UserId(user_id),
                telegram_chat_id=user_model.telegram_chat_id,
                account_ids=account_ids,
                today=datetime.now(UTC).date(),
            )
    finally:
        await engine.dispose()

    logger.info("digest triggered manually", user_id=user_id, result=digest_result.reason)
    return DigestResponse(
        sent=digest_result.sent,
        count=digest_result.count,
        reason=digest_result.reason,
    )


def _parse_user_uuid(user_id: str) -> object:
    import uuid

    try:
        return uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid user_id format") from exc
