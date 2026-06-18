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
        vertical=model.vertical,
        organization_id=str(model.organization_id) if model.organization_id else None,
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
    if account.organization_id is not None:
        model.organization_id = uuid.UUID(account.organization_id)
    return model


class SqlGoogleAdsAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, account_id: AccountId) -> GoogleAdsAccount | None:
        result = await self._session.execute(
            select(GoogleAdsAccountModel).where(GoogleAdsAccountModel.id == uuid.UUID(account_id))
        )
        model = result.scalar_one_or_none()
        return _model_to_domain(model) if model else None

    async def list_for_user(self, user_id: UserId) -> list[GoogleAdsAccount]:
        # Deterministic ordering (oldest connection first, id as tiebreak) so
        # callers that use accounts[0] as the "primary" account always resolve
        # to the same account across requests. Without an explicit ORDER BY,
        # Postgres row order is arbitrary, which made the displayed account and
        # the account targeted by mutations diverge for multi-account users.
        result = await self._session.execute(
            select(GoogleAdsAccountModel)
            .where(GoogleAdsAccountModel.user_id == uuid.UUID(user_id))
            .order_by(
                GoogleAdsAccountModel.connected_at.asc(),
                GoogleAdsAccountModel.id.asc(),
            )
        )
        return [_model_to_domain(m) for m in result.scalars().all()]

    async def get_by_customer_id(self, customer_id: str) -> GoogleAdsAccount | None:
        """Return the account row for a Google Ads customer_id, whoever owns it.

        Used by the linking task to detect a cross-user link and *transfer* the
        account to the user who just proved control of it via OAuth (reusing the
        existing row id so the move doesn't violate the unique customer_id index).
        """
        result = await self._session.execute(
            select(GoogleAdsAccountModel).where(GoogleAdsAccountModel.customer_id == customer_id)
        )
        model = result.scalar_one_or_none()
        return _model_to_domain(model) if model else None

    async def owner_of_customer_id(self, customer_id: str) -> UserId | None:
        """Return the user_id that owns this Google Ads customer_id, if any.

        Used to enforce one-Google-Ads-account-per-Adswise-user: a customer_id
        already linked to a different user must not be linked again (otherwise a
        user could dodge a subscription by opening a second account).
        """
        result = await self._session.execute(
            select(GoogleAdsAccountModel.user_id).where(
                GoogleAdsAccountModel.customer_id == customer_id
            )
        )
        row = result.first()
        return UserId(str(row[0])) if row else None

    async def list_active(self) -> list[GoogleAdsAccount]:
        """Return all accounts that do not need re-authentication."""
        result = await self._session.execute(
            select(GoogleAdsAccountModel).where(
                GoogleAdsAccountModel.needs_reauth == False  # noqa: E712
            )
        )
        return [_model_to_domain(m) for m in result.scalars().all()]

    async def delete(self, account_id: AccountId) -> bool:
        """Delete account row. Returns True if a row was actually deleted."""
        result = await self._session.execute(
            select(GoogleAdsAccountModel).where(GoogleAdsAccountModel.id == uuid.UUID(account_id))
        )
        model = result.scalar_one_or_none()
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    async def save(self, account: GoogleAdsAccount) -> GoogleAdsAccount:
        result = await self._session.execute(
            select(GoogleAdsAccountModel).where(GoogleAdsAccountModel.id == uuid.UUID(account.id))
        )
        existing = result.scalar_one_or_none()
        model = _domain_to_model(account, existing)
        if existing is None:
            self._session.add(model)
        await self._session.flush()
        return _model_to_domain(model)
