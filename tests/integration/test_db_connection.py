import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text


@pytest.mark.integration
async def test_db_connection(db_session: AsyncSession) -> None:
    """Verify that the database connection works via the db_session fixture."""
    result = await db_session.execute(text("SELECT 1 AS value"))
    row = result.fetchone()
    assert row is not None
    assert row[0] == 1
