#!/usr/bin/env python3
"""Start a throwaway PostgreSQL + pgvector instance for local development.

**This is a convenience for machines without Docker, not the deployment
target.** `docker-compose.yml` (pgvector/pgvector:pg16) remains the intended
local database, and a hosted Postgres remains the intended production one.
What this adds is a third option for the very common case of "I want to run
the tests on this laptop right now and I do not have Docker installed":
`pgserver` is a pip-installable, self-contained PostgreSQL build that ships
pgvector, needs no admin rights and no reboot, and stores its whole cluster
in one directory you can delete.

It is a real PostgreSQL server, so every pgvector code path — the HNSW index,
the `<=>` cosine operator, the vector(768) column — is exercised for real.
Nothing about the application changes; only where DATABASE_URL points.

Usage:
    python scripts/dev_db.py start      # start it and print DATABASE_URL
    python scripts/dev_db.py url        # print DATABASE_URL (starting if needed)
    python scripts/dev_db.py stop       # shut the server down
    python scripts/dev_db.py reset      # delete the data directory entirely

Typical flow:
    python scripts/dev_db.py start
    cd apps/api && alembic upgrade head && pytest
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# Kept out of the repo tree entirely so a stray `git add .` can never commit a
# database cluster. `.gitignore` also covers pgdata/ for the docker path.
DATA_DIR = REPO_ROOT / ".devdb"
DB_NAME = "campusplus"


def _pgserver():
    try:
        import pgserver
    except ImportError:
        sys.exit(
            "pgserver is not installed. It is a dev-only dependency:\n"
            "    pip install pgserver\n"
            "Or use Docker instead: docker compose up -d"
        )
    return pgserver


def _async_url(sync_url: str) -> str:
    """Rewrite psycopg's URL scheme to the asyncpg one the app uses."""
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgresql://"):
        if sync_url.startswith(prefix):
            return "postgresql+asyncpg://" + sync_url[len(prefix) :]
    return sync_url


async def _ensure_database(admin_url: str) -> None:
    """Create the application database if it is not there yet.

    Done over a normal asyncpg connection rather than through pgserver's own
    `psql` helper: that helper shells out, and it mis-quotes paths containing
    a space (which "C:\\Users\\First Last\\..." very much does), failing
    silently and leaving the database uncreated.
    """
    import asyncpg

    conn = await asyncpg.connect(admin_url)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", DB_NAME
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{DB_NAME}"')
    finally:
        await conn.close()


def start() -> str:
    import asyncio

    pgserver = _pgserver()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(str(DATA_DIR), cleanup_mode=None)

    # `get_server` hands back a URI for the default database; make sure the
    # application's own database exists next to it.
    admin_url = server.get_uri()
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://"):
        if admin_url.startswith(prefix):
            admin_url = "postgresql://" + admin_url[len(prefix) :]
    asyncio.run(_ensure_database(admin_url))

    return _async_url(server.get_uri(database=DB_NAME))


def stop() -> None:
    pgserver = _pgserver()
    if not DATA_DIR.exists():
        print("No dev database directory — nothing to stop.")
        return
    server = pgserver.get_server(str(DATA_DIR), cleanup_mode=None)
    server.cleanup()
    print("Stopped.")


def reset() -> None:
    import shutil

    stop()
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR, ignore_errors=True)
    print(f"Removed {DATA_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "url", "stop", "reset"])
    args = parser.parse_args()

    if args.command in {"start", "url"}:
        url = start()
        if args.command == "start":
            print("PostgreSQL + pgvector is running.\n")
            print(f"  DATABASE_URL={url}\n")
            print("Next:")
            print("  cd apps/api && alembic upgrade head")
            print("  uvicorn app.main:app --reload --port 8000")
        else:
            print(url)
    elif args.command == "stop":
        stop()
    elif args.command == "reset":
        reset()


if __name__ == "__main__":
    main()
