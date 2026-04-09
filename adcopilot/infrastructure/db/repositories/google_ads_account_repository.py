import uuid
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import AccountId, GoogleAdsAccount, UserId
from adcopilot.infrastructure.db.models import GoogleAdsAccountModel


def _model_to_domain(model: GoogleAdsAccountModel) -> GoogleAdsAccount:
    return GoogleAdsAccount(
        id=AccountId(str(model.id)),
        user_id=UserId(str(model.user_id)),
        customer_id=model.customer_id,
        descriptive_name=model.descriptive_name,
        currency=model.currency,
        timezone=model.timezone,
        is_manager=model.is_manager,
        write_enabled=model.write_enabled,
        needs_reauth=model.needs_reauth,
        connected_at=model.connected_at.replace(tzinfo=UTC)
        if model.connected_at.tzinfo is None
        else model.connected_at,
    )


def _domain_to_model(
    account: GoogleAdsAccount, existing: GoogleAdsAccountModel | None = None
) -> GoogleAdsAccountModel:
    model = existing or GoogleAdsAccountModel()
    model.id = uuid.UUID(account.id)
    model.user_id = uuid.UUID(account.user_id)
    model.customer_id = account.customer_id
    model.descriptive_name = account.descriptive_name
    model.currency = account.currency
    model.timezone = account.timezone
    model.is_manager = account.is_manager
    model.write_enabled = account.write_enabled
    model.needs_reauth = account.needs_reauth
    model.connected_at = account.connected_at
    return model


class SqlGoogleAdsAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, account_id: AccountId) -> GoogleAdsAccount | None:
        result = await self._session.execute(
            select(GoogleAdsAccountModel).where(
                GoogleAdsAccountModel.id == uuid.UUID(account_id)
            )
        )
        model = result.scalar_one_or_none()
        return _model_to_domain(model) if model else None

    async def list_for_user(self, user_id: UserId) -> list[GoogleAdsAccount]:
        result = await self._session.execute(
            select(GoogleAdsAccountModel).where(
                GoogleAdsAccountModel.user_id == uuid.UUID(user_id)
            )
        )
        return [_model_to_domain(m) for m in result.scalars().all()]

    async def list_active(self) -> list[GoogleAdsAccount]:
        """Return all accounts that do not need re-authentication."""
        result = await self._session.execute(
            select(GoogleAdsAccountModel).where(
                GoogleAdsAccountModel.needs_reauth == False  # noqa: E712
            )
        )
        return [_model_to_domain(m) for m in result.scalars().all()]

    async def save(self, account: GoogleAdsAccount) -> GoogleAdsAccount:
        result = await self._session.execute(
            select(GoogleAdsAccountModel).where(
                GoogleAdsAccountModel.id == uuid.UUID(account.id)
            )
        )
        existing = result.scalar_one_or_none()
        model = _domain_to_model(account, existing)
        if existing is None:
            self._session.add(model)
        await self._session.flush()
        return _model_to_domain(model)
