"""Shared pytest configuration and database fixtures.

The pure-logic tests (cluster, priority, providers, storage, ask filters)
need nothing but Python and always run. The integration tests need a real
Postgres with pgvector, because `UUID` columns, the `vector(768)` column and
the `<=>` cosine operator have no sqlite equivalent worth faking — a sqlite
stand-in would test a different system than the one that ships.

So rather than failing when no database is around, those tests skip with a
message that says exactly how to get one. `RUN_DB_TESTS=1` turns the skip
into a hard failure, which is what CI should set: on a machine that is
supposed to have a database, a silent skip is worse than a red test.

**Event loop scoping.** `app.db.database` builds one module-level async
engine, so its connection pool belongs to whichever loop first used it.
Every async fixture and test that touches the database therefore runs on the
*session* loop (`loop_scope="session"`), or asyncpg raises "got Future
attached to a different loop" the moment a pooled connection crosses a loop
boundary. This is why the DB test modules carry
`pytest.mark.asyncio(loop_scope="session")` rather than a bare
`pytest.mark.asyncio`.

A corollary worth knowing before it costs someone an afternoon: **do not
call `asyncio.run()` in a test module that sorts alphabetically before
`test_pipeline_db.py`.** It closes the session loop those tests share, and
they all then fail with "coroutine was never awaited" — a failure a long
way from its cause. Mark the test
`@pytest.mark.asyncio(loop_scope="session")` and `await` instead.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import async_session_factory, engine

SKIP_REASON = (
    "No Postgres+pgvector reachable at DATABASE_URL. Start one with "
    "`docker compose up -d` (or `python scripts/dev_db.py start` if you have "
    "no Docker), then `cd apps/api && alembic upgrade head`. Set "
    "RUN_DB_TESTS=1 to make this a failure instead of a skip."
)


async def _database_available() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            # A connection is not enough: the schema has to be migrated, or
            # every test below fails on a missing table rather than skipping.
            await conn.execute(text("SELECT 1 FROM complaints LIMIT 1"))
            await conn.execute(text("SELECT 1 FROM complaint_clusters LIMIT 1"))
        return True
    except Exception:
        return False


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def database_ready() -> AsyncGenerator[bool, None]:
    available = await _database_available()
    if not available and os.getenv("RUN_DB_TESTS"):
        pytest.fail(SKIP_REASON)
    yield available
    # Return pooled connections before the session loop closes, so teardown
    # does not surface as a pile of "Event loop is closed" noise.
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db(database_ready: bool) -> AsyncGenerator[AsyncSession, None]:
    """A session whose writes are always rolled back.

    Standard SQLAlchemy "join an external transaction" pattern: application
    code calling `commit()` commits a savepoint inside our outer
    transaction, which we then roll back — so a test can exercise the real
    commit path without leaving anything behind.
    """
    if not database_ready:
        pytest.skip(SKIP_REASON)

    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            if outer.is_active:
                await outer.rollback()


@pytest_asyncio.fixture(loop_scope="session")
async def clean_db(database_ready: bool) -> AsyncGenerator[AsyncSession, None]:
    """A committed-for-real session that truncates complaint data afterwards.

    A few things genuinely cannot be tested inside a rolled-back
    transaction — most importantly the pgvector index path, which needs the
    rows to be visible to a fresh query planner. This fixture therefore
    commits normally and cleans up by truncating, leaving the seeded
    departments and categories (reference data from migration 0001) intact.
    """
    if not database_ready:
        pytest.skip(SKIP_REASON)

    async with async_session_factory() as session:
        await _truncate(session)
        try:
            yield session
        finally:
            await _truncate(session)


async def _truncate(session: AsyncSession) -> None:
    # A failing test can leave the session mid-transaction; roll back first
    # so cleanup runs on a healthy connection rather than raising
    # PendingRollbackError and masking the real failure.
    await session.rollback()
    await session.execute(
        text(
            "TRUNCATE status_events, complaint_embeddings, complaints, "
            "complaint_clusters RESTART IDENTITY CASCADE"
        )
    )
    await session.commit()
