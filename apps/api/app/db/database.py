"""Async SQLAlchemy engine + session setup.

Reads `DATABASE_URL` from `app.config.get_settings()` — nothing here should
read the env directly (see AGENTS.md's config convention). Import `get_db`
as a FastAPI dependency to get an `AsyncSession` scoped to one request.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in `app.db.models`.

    Alembic's `env.py` imports `Base.metadata` as the autogenerate target,
    so every model must be declared against this base (and imported
    somewhere Alembic reaches) to be picked up by migrations.
    """


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped `AsyncSession`.

    Usage: `db: AsyncSession = Depends(get_db)` in a router function.
    """
    async with async_session_factory() as session:
        yield session
