"""Authentication endpoints — signup and login."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import Settings, get_settings
from adcopilot.domain.entities import PlanTier, User, UserId
from adcopilot.rate_limit import limiter

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_DAYS = 30

# Rate limits applied to auth endpoints.
# Both limits are per source IP as extracted by _get_real_ip() in rate_limit.py.
_LOGIN_LIMIT = "5/minute"
_SIGNUP_LIMIT = "5/minute"


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    user_id: str
    email: str
    token: str


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _make_jwt(user_id: str, secret_key: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(UTC) + timedelta(days=_JWT_EXPIRY_DAYS),
        "iat": datetime.now(UTC),
    }
    token: str = jwt.encode(payload, secret_key, algorithm=_JWT_ALGORITHM)
    return token


@router.post("/signup", response_model=AuthResponse)
@limiter.limit(_SIGNUP_LIMIT)
async def signup(
    request: Request,  # Required by slowapi for per-route rate limiting
    body: SignupRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
    """Create a new user account."""
    from sqlalchemy import select

    from adcopilot.infrastructure.db.models import UserModel
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            # Check if email already taken
            result = await session.execute(select(UserModel).where(UserModel.email == body.email))
            if result.scalar_one_or_none() is not None:
                raise HTTPException(status_code=409, detail="Email already registered")

            user = User(
                id=UserId(str(uuid.uuid4())),
                email=body.email,
                telegram_chat_id=None,
                created_at=datetime.now(UTC),
                plan=PlanTier.STARTER,
                password_hash=_hash_password(body.password),
            )
            repo = SqlUserRepository(session)
            saved = await repo.save(user)
            await session.commit()
    finally:
        await engine.dispose()

    from adcopilot.observability import set_user_context

    set_user_context(saved.id)
    token = _make_jwt(saved.id, settings.SECRET_KEY)
    logger.info("user signed up", user_id=saved.id)
    return AuthResponse(user_id=saved.id, email=saved.email, token=token)


@router.post("/login", response_model=AuthResponse)
@limiter.limit(_LOGIN_LIMIT)
async def login(
    request: Request,  # Required by slowapi for per-route rate limiting
    body: LoginRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
    """Authenticate with email + password."""
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            repo = SqlUserRepository(session)
            user = await repo.get_by_email(body.email)
    finally:
        await engine.dispose()

    if user is None or user.password_hash is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    from adcopilot.observability import set_user_context

    set_user_context(user.id)
    token = _make_jwt(user.id, settings.SECRET_KEY)
    logger.info("user logged in", user_id=user.id)
    return AuthResponse(user_id=user.id, email=user.email, token=token)
