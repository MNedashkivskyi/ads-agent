import uuid
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import PlanTier, User, UserId
from adcopilot.infrastructure.db.models import UserModel


def _model_to_domain(model: UserModel) -> User:
    return User(
        id=UserId(str(model.id)),
        email=model.email,
        telegram_chat_id=model.telegram_chat_id,
        created_at=model.created_at.replace(tzinfo=UTC)
        if model.created_at.tzinfo is None
        else model.created_at,
        plan=PlanTier(model.plan),
        notifications_paused=model.notifications_paused,
        password_hash=model.password_hash,
        notification_hour=model.notification_hour,
        language=model.language,
        stripe_customer_id=model.stripe_customer_id,
        subscription_status=model.subscription_status,
        trial_ends_at=model.trial_ends_at,
        subscription_id=model.subscription_id,
    )


def _domain_to_model(user: User, existing: UserModel | None = None) -> UserModel:
    model = existing or UserModel()
    model.id = uuid.UUID(user.id)
    model.email = user.email
    model.telegram_chat_id = user.telegram_chat_id
    model.plan = user.plan.value
    model.notifications_paused = user.notifications_paused
    model.password_hash = user.password_hash
    model.notification_hour = user.notification_hour
    model.language = user.language
    model.stripe_customer_id = user.stripe_customer_id
    model.subscription_status = user.subscription_status
    model.trial_ends_at = user.trial_ends_at
    model.subscription_id = user.subscription_id
    return model


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UserId) -> User | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.id == uuid.UUID(user_id))
        )
        model = result.scalar_one_or_none()
        return _model_to_domain(model) if model else None

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        model = result.scalar_one_or_none()
        return _model_to_domain(model) if model else None

    async def save(self, user: User) -> User:
        result = await self._session.execute(
            select(UserModel).where(UserModel.id == uuid.UUID(user.id))
        )
        existing = result.scalar_one_or_none()
        model = _domain_to_model(user, existing)
        if existing is None:
            self._session.add(model)
        await self._session.flush()
        return _model_to_domain(model)
