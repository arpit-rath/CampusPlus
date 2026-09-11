"""HTTP-layer tests: the routes, their contracts, and admin access control.

These drive the real ASGI app against a real database, so they cover the
things a unit test of the pipeline cannot: response shapes the frontend
depends on, status codes, validation, and whether `ADMIN_TOKEN` is actually
enforced.

Skips cleanly with an explanatory message when no database is reachable —
see `conftest.py`.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.db.database import get_db
from app.main import app

# Session-scoped loop: the app builds one module-level async engine, so
# its pooled connections must never cross an event loop. See conftest.py.
pytestmark = pytest.mark.asyncio(loop_scope="session")

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


@pytest_asyncio.fixture(loop_scope="session")
async def client(clean_db) -> AsyncGenerator[AsyncClient, None]:
    """An HTTP client wired to the app, sharing the test's own session."""

    async def _override_get_db():
        yield clean_db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http:
            yield http
    finally:
        app.dependency_overrides.pop(get_db, None)


# --- system ---------------------------------------------------------------


async def test_health_reports_configuration_honestly():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # The point of these fields: nobody should have to guess whether a demo
    # is really hitting Gemini, or whether the admin API is open.
    assert body["llm_effective"] in {"gemini", "mock"}
    assert body["admin_auth"] in {"enabled", "disabled"}
    assert body["thresholds"]["duplicate"] == get_settings().duplicate_threshold


# --- reference data -------------------------------------------------------


async def test_seeded_departments_and_categories_are_served(client):
    departments = (await client.get("/departments")).json()
    categories = (await client.get("/categories")).json()

    assert len(departments) >= 5
    slugs = {c["slug"] for c in categories}
    assert {"wifi", "electrical", "sanitation", "infrastructure", "academics", "other"} <= slugs


# --- complaint creation ---------------------------------------------------


async def test_create_complaint_returns_the_full_frontend_contract(client):
    response = await client.post(
        "/complaints",
        json={
            "description": "The wifi is completely down in Innovation Hall, nobody can connect.",
            "location_building": "Innovation Hall",
            "location_room": "204",
            "student_id": "student_a",
        },
    )
    assert response.status_code == 201
    body = response.json()

    # Every field apps/web/src/lib/api.ts reads.
    for field in (
        "id", "raw_description", "photo_url", "photo_matches_text",
        "location_building", "location_room", "category_slug", "department_name",
        "severity", "safety_flag", "priority_score", "priority_breakdown",
        "status", "ai_summary", "cluster_id", "is_recurring",
        "cluster_member_count", "independent_student_count", "created_at",
    ):
        assert field in body, f"missing {field} from the complaint contract"

    assert body["category_slug"] == "wifi"
    assert body["department_name"], "a categorized complaint must be routed"
    assert body["status"] == "open"
    assert set(body["priority_breakdown"]) == {"severity", "frequency", "safety", "sla_age"}
    assert body["priority_score"] == pytest.approx(
        sum(body["priority_breakdown"].values()), abs=1e-6
    )


async def test_create_complaint_records_who_filed_it(client):
    """The report form requires a name and a role; the API stores both.

    They are description rather than identity — `student_id` is still what
    the recurring rule counts — so they round-trip untouched and do not
    affect clustering.
    """
    response = await client.post(
        "/complaints",
        json={
            "description": "The projector in seminar room 2 cuts out every few minutes.",
            "location_building": "Academic Block A",
            "location_room": "Seminar room 2",
            "student_id": "teacher:meera-singh",
            "reporter_name": "Dr Meera Singh",
            "reporter_role": "teacher",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["reporter_name"] == "Dr Meera Singh"
    assert body["reporter_role"] == "teacher"
    assert body["student_id"] == "teacher:meera-singh"


async def test_reporter_role_is_a_closed_set(client):
    """Free text here would split one group across three spellings."""
    response = await client.post(
        "/complaints",
        json={
            "description": "The lift in Academic Block B has been stuck since morning.",
            "location_building": "Academic Block B",
            "reporter_name": "Someone",
            "reporter_role": "principal",
        },
    )
    assert response.status_code == 422


async def test_a_complaint_can_still_be_filed_without_a_reporter(client):
    """Every complaint seeded before the form asked has neither field, and
    the seed script still posts without them."""
    response = await client.post(
        "/complaints",
        json={
            "description": "The water cooler on the second floor is leaking again.",
            "location_building": "Main Library",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["reporter_name"] is None
    assert body["reporter_role"] is None


async def test_create_complaint_rejects_empty_description(client):
    response = await client.post(
        "/complaints", json={"description": "", "location_building": "Innovation Hall"}
    )
    assert response.status_code == 422


async def test_create_complaint_requires_a_building(client):
    response = await client.post("/complaints", json={"description": "something broke"})
    assert response.status_code == 422


async def test_create_complaint_stores_a_valid_photo(client):
    response = await client.post(
        "/complaints",
        json={
            "description": "Sparking wires near the panel.",
            "location_building": "Hostel Block B",
            "photo_base64": f"data:image/png;base64,{PNG}",
        },
    )
    assert response.status_code == 201
    body = response.json()
    # A URL, not a giant base64 blob echoed back into the row.
    assert body["photo_url"].startswith("/uploads/")
    assert len(body["photo_url"]) < 100
    assert body["photo_matches_text"] is not None


async def test_create_complaint_rejects_a_non_image_attachment(client):
    response = await client.post(
        "/complaints",
        json={
            "description": "Sparking wires near the panel.",
            "location_building": "Hostel Block B",
            "photo_base64": "data:image/png;base64,"
            + base64.b64encode(b"<html>not an image</html>").decode(),
        },
    )
    assert response.status_code == 422
    assert "image" in response.json()["detail"]


async def test_complaint_without_a_photo_has_null_photo_verification(client):
    """NULL means "no photo", which is not the same as "photo did not match"."""
    body = (
        await client.post(
            "/complaints",
            json={"description": "Broken chair in LH-3.", "location_building": "Academic Block A"},
        )
    ).json()
    assert body["photo_url"] is None
    assert body["photo_matches_text"] is None


# --- reading --------------------------------------------------------------


async def test_get_complaint_and_its_event_timeline(client):
    created = (
        await client.post(
            "/complaints",
            json={"description": "Toilets clogged on the 2nd floor.", "location_building": "Science Block"},
        )
    ).json()

    fetched = await client.get(f"/complaints/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]

    events = (await client.get(f"/complaints/{created['id']}/events")).json()
    assert len(events) == 1
    assert events[0]["status"] == "open"


async def test_get_missing_complaint_is_404(client):
    response = await client.get("/complaints/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_list_complaints_is_priority_sorted_and_filterable(client):
    await client.post(
        "/complaints",
        json={"description": "Minor scuff on a wall.", "location_building": "Main Library"},
    )
    await client.post(
        "/complaints",
        json={
            "description": "Exposed sparking wiring near the panel, completely dangerous.",
            "location_building": "Hostel Block B",
        },
    )

    everything = (await client.get("/complaints")).json()
    assert len(everything) == 2
    scores = [c["priority_score"] for c in everything]
    assert scores == sorted(scores, reverse=True)

    filtered = (await client.get("/complaints?building=Hostel Block B")).json()
    assert len(filtered) == 1
    assert filtered[0]["location_building"] == "Hostel Block B"

    by_status = (await client.get("/complaints?status=resolved")).json()
    assert by_status == []


# --- clusters -------------------------------------------------------------


async def test_clusters_endpoint_exposes_real_clusters(client):
    for student in ("student_a", "student_b", "student_c"):
        await client.post(
            "/complaints",
            json={
                "description": "Water is leaking from the ceiling in the Block A hostel corridor.",
                "location_building": "Hostel Block A",
                "student_id": student,
            },
        )

    clusters = (await client.get("/clusters")).json()
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster["independent_student_count"] == 3
    assert cluster["is_recurring"] is True
    assert cluster["representative_complaint_id"]

    detail = (await client.get(f"/clusters/{cluster['id']}")).json()
    assert len(detail["members"]) == 3

    recurring_only = (await client.get("/clusters?recurring_only=true")).json()
    assert len(recurring_only) == 1


# --- admin ----------------------------------------------------------------


async def test_admin_routes_are_open_when_no_token_is_configured(client):
    assert get_settings().admin_token == "", "this test assumes the dev default"
    response = await client.get("/admin/stats")
    assert response.status_code == 200


async def test_admin_routes_are_enforced_once_a_token_is_configured(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_token", "s3cret")

    assert (await client.get("/admin/stats")).status_code == 401
    assert (
        await client.get("/admin/stats", headers={"X-Admin-Token": "wrong"})
    ).status_code == 401
    assert (
        await client.get("/admin/stats", headers={"X-Admin-Token": "s3cret"})
    ).status_code == 200


async def test_status_changes_are_gated_by_the_admin_token(client, monkeypatch):
    created = (
        await client.post(
            "/complaints",
            json={"description": "Broken lock on the gate.", "location_building": "Main Gate"},
        )
    ).json()

    monkeypatch.setattr(get_settings(), "admin_token", "s3cret")
    unauthorized = await client.patch(
        f"/complaints/{created['id']}/status", json={"status": "resolved"}
    )
    assert unauthorized.status_code == 401

    authorized = await client.patch(
        f"/complaints/{created['id']}/status",
        json={"status": "resolved", "note": "Fixed by facilities"},
        headers={"X-Admin-Token": "s3cret"},
    )
    assert authorized.status_code == 200
    assert authorized.json()["status"] == "resolved"

    events = (await client.get(f"/complaints/{created['id']}/events")).json()
    assert [e["status"] for e in events] == ["open", "resolved"]


async def test_admin_can_override_routing(client):
    created = (
        await client.post(
            "/complaints",
            json={"description": "The wifi is down in the library.", "location_building": "Main Library"},
        )
    ).json()
    departments = (await client.get("/departments")).json()
    target = next(d for d in departments if d["name"] != created["department_name"])

    response = await client.patch(
        f"/admin/complaints/{created['id']}/route",
        json={"department_id": target["id"], "note": "Handled by facilities instead"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["department_name"] == target["name"]
    assert body["department_overridden"] is True


async def test_admin_ask_returns_a_grounded_answer(client):
    await client.post(
        "/complaints",
        json={
            "description": "The wifi is completely down in Innovation Hall.",
            "location_building": "Innovation Hall",
        },
    )
    response = await client.post("/admin/ask", json={"question": "any wifi problems?"})
    assert response.status_code == 200
    body = response.json()
    assert body["matched_count"] == 1
    assert len(body["cited_complaint_ids"]) == 1
    assert "wifi" in body["filters"]


async def test_admin_stats_and_digest(client):
    await client.post(
        "/complaints",
        json={"description": "Overflowing bins outside the cafeteria.", "location_building": "Cafeteria"},
    )

    stats = (await client.get("/admin/stats")).json()
    assert stats["open"] == 1
    assert stats["resolved"] == 0

    digest = (await client.get("/admin/digest?window_days=7")).json()
    assert digest["total_complaints"] == 1
    assert digest["top_buildings"][0]["label"] == "Cafeteria"
    assert len(digest["headline_issues"]) == 1


async def test_deleting_a_complaint_requires_admin_and_recounts_its_cluster(client, monkeypatch):
    ids = []
    for student in ("student_a", "student_b", "student_c"):
        body = (
            await client.post(
                "/complaints",
                json={
                    "description": "Water is leaking from the ceiling in the Block A hostel corridor.",
                    "location_building": "Hostel Block A",
                    "student_id": student,
                },
            )
        ).json()
        ids.append(body["id"])

    monkeypatch.setattr(get_settings(), "admin_token", "s3cret")
    assert (await client.delete(f"/complaints/{ids[-1]}")).status_code == 401

    deleted = await client.delete(
        f"/complaints/{ids[-1]}", headers={"X-Admin-Token": "s3cret"}
    )
    assert deleted.status_code == 204

    clusters = (await client.get("/clusters", headers={"X-Admin-Token": "s3cret"})).json()
    assert clusters[0]["member_count"] == 2
    assert clusters[0]["independent_student_count"] == 2
    assert clusters[0]["is_recurring"] is False, "dropping below 3 students undoes recurring"
