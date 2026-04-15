import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.infrastructure.db.models import Base


def get_test_db_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://adcopilot:adcopilot@localhost:5432/adcopilot_test",
    )


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an AsyncSession for each test with full rollback isolation.

    Uses NullPool so every connect() opens a brand-new asyncpg connection
    in the current event loop — no cross-loop Future issues.
    """
    url = get_test_db_url()
    engine = create_async_engine(url, echo=False, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()

    await engine.dispose()
