import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from adcopilot.infrastructure.db.models import Base


def get_test_db_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://adcopilot:adcopilot@localhost:5432/adcopilot_test",
    )


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    url = get_test_db_url()
    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    async with db_engine.connect() as conn:
        await conn.begin_nested()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.rollback()
        await session.close()
