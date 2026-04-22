"""Async SQLAlchemy engine factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from adcopilot.config import Settings


def build_async_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.DATABASE_URL)
