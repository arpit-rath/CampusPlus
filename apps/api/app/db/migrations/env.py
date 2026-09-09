"""Alembic environment — wired to our async engine and to Base.metadata.

Runs migrations through the same async driver (asyncpg) the app uses,
following SQLAlchemy's documented "async migrations" recipe: an async
engine is created just for the migration run, and the actual sync-style
migration work happens inside `connection.run_sync(...)`.

The connection URL and the models' metadata both come from the app itself
(`app.config.get_settings()` / `app.db.models`) rather than being
duplicated here, so there is exactly one place that defines the schema and
exactly one place that defines the DB URL.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.config import get_settings

# Import Base (and, transitively, every model) so Base.metadata is fully
# populated before Alembic reads target_metadata.
from app.db.database import Base
from app.db import models  # noqa: F401  (populates Base.metadata as a side effect)

# Alembic Config object, giving access to values in alembic.ini.
config = context.config

# Interpret the config file for Python logging, if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Override sqlalchemy.url from app settings (alembic.ini leaves it blank).
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL, no DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async Engine for this migration run and connect."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live async connection."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
