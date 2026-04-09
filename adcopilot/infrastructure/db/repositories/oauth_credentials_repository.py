import uuid
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import AccountId, OAuthCredentials
from adcopilot.infrastructure.db.encryption import decrypt, encrypt
from adcopilot.infrastructure.db.models import OAuthCredentialsModel


def _model_to_domain(model: OAuthCredentialsModel, key: str) -> OAuthCredentials:
    return OAuthCredentials(
        account_id=AccountId(str(model.account_id)),
        refresh_token=decrypt(model.refresh_token_encrypted, key),
        access_token=decrypt(model.access_token_encrypted, key)
        if model.access_token_encrypted
        else None,
        expires_at=model.expires_at.replace(tzinfo=UTC)
        if model.expires_at and model.expires_at.tzinfo is None
        else model.expires_at,
    )


class SqlOAuthCredentialsRepository:
    def __init__(self, session: AsyncSession, encryption_key: str) -> None:
        self._session = session
        self._key = encryption_key

    async def get(self, account_id: AccountId) -> OAuthCredentials | None:
        result = await self._session.execute(
            select(OAuthCredentialsModel).where(
                OAuthCredentialsModel.account_id == uuid.UUID(account_id)
            )
        )
        model = result.scalar_one_or_none()
        return _model_to_domain(model, self._key) if model else None

    async def save(self, credentials: OAuthCredentials) -> OAuthCredentials:
        result = await self._session.execute(
            select(OAuthCredentialsModel).where(
                OAuthCredentialsModel.account_id == uuid.UUID(credentials.account_id)
            )
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            model = OAuthCredentialsModel()
            model.account_id = uuid.UUID(credentials.account_id)
            self._session.add(model)
        else:
            model = existing

        model.refresh_token_encrypted = encrypt(credentials.refresh_token, self._key)
        model.access_token_encrypted = (
            encrypt(credentials.access_token, self._key) if credentials.access_token else None
        )
        model.expires_at = credentials.expires_at

        await self._session.flush()
        return _model_to_domain(model, self._key)
