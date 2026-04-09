from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import get_settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info("adcopilot starting", env=settings.ENV)
    yield
    logger.info("adcopilot shutting down")


def create_app() -> FastAPI:
    application = FastAPI(title="AdCopilot", version="0.1.0", lifespan=lifespan)

    @application.get("/health")
    async def health() -> JSONResponse:
        settings = get_settings()
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        try:
            async with AsyncSession(engine) as session:
                await session.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception as exc:
            logger.warning("health check db failed", error=str(exc))
            db_status = "error"
        finally:
            await engine.dispose()

        status_code = 200 if db_status == "ok" else 503
        return JSONResponse(
            status_code=status_code,
            content={"status": "ok" if db_status == "ok" else "degraded", "db": db_status},
        )

    return application


app = create_app()
