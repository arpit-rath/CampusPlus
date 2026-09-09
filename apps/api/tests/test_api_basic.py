"""Basic CRUD tests for the complaints/departments/categories routers.

These hit a real Postgres+pgvector database (via `DATABASE_URL`, same as
the app) rather than mocking the DB layer — there's no sqlite fallback
here since `UUID` and `Vector` columns are Postgres/pgvector-specific.
Run `docker compose up -d && alembic upgrade head` first so the schema
and seed data (departments/categories) exist, then:

    cd apps/api && pytest tests/test_api_basic.py -v

Each test runs inside an outer DB transaction that is rolled back in a
fixture teardown, so nothing written by a test persists — the seeded
departments/categories from the `0001_init` migration are relied on as
read-only fixture data (never mutated here).

This module was written without a working `pip install` in this
environment (see CLAUDE.md's scaffold note) — it has been checked by
careful reading, not by execution.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import engine, get_db
from app.routers import categories, complaints, departments


def _build_test_app() -> FastAPI:
    """A standalone app wired to our three routers.

    `app.main` only wires up routers during the integration pass (see the
    commented-out block there), so tests build their own minimal app
    instead of depending on that having happened yet.
    """
    test_app = FastAPI()
    test_app.include_router(complaints.router, prefix="/complaints", tags=["complaints"])
    test_app.include_router(departments.router, prefix="/departments", tags=["departments"])
    test_app.include_router(categories.router, prefix="/categories", tags=["categories"])
    return test_app


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """One AsyncSession per test, wrapped in a transaction that is always
    rolled back — the standard SQLAlchemy 2.0 "join an external
    transaction" pattern for isolated test writes. Router code calling
    `db.commit()` commits a savepoint, not the outer transaction, so
    nothing escapes this test.
    """
    async with engine.connect() as conn:
        outer_txn = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await outer_txn.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app = _build_test_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Seed data -------------------------------------------------------------


@pytest.mark.asyncio
async def test_seeded_categories_and_departments(client: AsyncClient) -> None:
    cat_resp = await client.get("/categories")
    assert cat_resp.status_code == 200
    slugs = {c["slug"] for c in cat_resp.json()}
    assert {"wifi", "electrical", "sanitation", "infrastructure", "academics", "other"} <= slugs

    dept_resp = await client.get("/departments")
    assert dept_resp.status_code == 200
    names = {d["name"] for d in dept_resp.json()}
    assert "IT & Network" in names
    assert "Facilities" in names


# --- Complaints CRUD ---------------------------------------------------


@pytest.mark.asyncio
async def test_create_complaint_defaults_to_open_and_unassigned(client: AsyncClient) -> None:
    payload = {
        "description": "WiFi is down across the whole 3rd floor of the library.",
        "location_building": "Library",
        "location_room": "3F",
    }
    resp = await client.post("/complaints", json=payload)
    assert resp.status_code == 201

    body = resp.json()
    assert body["raw_description"] == payload["description"]
    assert body["location_building"] == "Library"
    assert body["status"] == "open"
    # No AI pipeline has run against this row (that's Track B's job) — so
    # it should come back unassigned/zeroed, not guessed at here.
    assert body["category_slug"] is None
    assert body["department_name"] is None
    assert body["severity"] is None
    assert body["safety_flag"] is False
    assert body["priority_score"] == 0.0
    assert body["priority_breakdown"] == {
        "severity": 0.0,
        "frequency": 0.0,
        "safety": 0.0,
        "sla_age": 0.0,
    }
    assert body["is_recurring"] is False
    assert body["cluster_member_count"] == 0
    assert uuid.UUID(body["id"])  # a real UUID came back


@pytest.mark.asyncio
async def test_create_complaint_requires_location_building(client: AsyncClient) -> None:
    resp = await client.post("/complaints", json={"description": "No location given"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_complaint_roundtrip(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/complaints",
        json={"description": "Broken tube light", "location_building": "Block C"},
    )
    complaint_id = create_resp.json()["id"]

    get_resp = await client.get(f"/complaints/{complaint_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == complaint_id


@pytest.mark.asyncio
async def test_get_complaint_404_for_unknown_id(client: AsyncClient) -> None:
    resp = await client.get(f"/complaints/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_complaints_status_filter(client: AsyncClient) -> None:
    open_resp = await client.post(
        "/complaints",
        json={"description": "Leaking tap", "location_building": "Hostel A"},
    )
    to_resolve_resp = await client.post(
        "/complaints",
        json={"description": "Broken chair", "location_building": "Hostel A"},
    )
    open_id = open_resp.json()["id"]
    resolve_id = to_resolve_resp.json()["id"]

    patch_resp = await client.patch(
        f"/complaints/{resolve_id}/status",
        json={"status": "resolved", "note": "Fixed by facilities", "actor": "admin@campus.edu"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "resolved"

    open_list = await client.get("/complaints", params={"status": "open"})
    open_ids = {c["id"] for c in open_list.json()}
    assert open_id in open_ids
    assert resolve_id not in open_ids

    resolved_list = await client.get("/complaints", params={"status": "resolved"})
    resolved_ids = {c["id"] for c in resolved_list.json()}
    assert resolve_id in resolved_ids
    assert open_id not in resolved_ids


@pytest.mark.asyncio
async def test_update_status_rejects_unknown_status(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/complaints",
        json={"description": "Flickering lights", "location_building": "Block D"},
    )
    complaint_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/complaints/{complaint_id}/status", json={"status": "not_a_real_status"}
    )
    assert resp.status_code == 422


# --- Departments / categories CRUD --------------------------------------


@pytest.mark.asyncio
async def test_department_create_get_update_delete(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/departments",
        json={"name": "Test Ops Dept", "contact_email": "testops@campus.edu"},
    )
    assert create_resp.status_code == 201
    dept = create_resp.json()

    get_resp = await client.get(f"/departments/{dept['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Test Ops Dept"

    patch_resp = await client.patch(
        f"/departments/{dept['id']}", json={"contact_email": "new-testops@campus.edu"}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["contact_email"] == "new-testops@campus.edu"

    delete_resp = await client.delete(f"/departments/{dept['id']}")
    assert delete_resp.status_code == 204

    missing_resp = await client.get(f"/departments/{dept['id']}")
    assert missing_resp.status_code == 404


@pytest.mark.asyncio
async def test_category_requires_valid_department(client: AsyncClient) -> None:
    resp = await client.post(
        "/categories",
        json={"slug": "test-category", "default_department_id": str(uuid.uuid4())},
    )
    # default_department_id doesn't exist -> FK violation -> 409, not a 500.
    assert resp.status_code == 409
