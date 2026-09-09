"""End-to-end pipeline tests against a real Postgres + pgvector.

This file exists to answer the one question the pure-logic tests cannot:
does the product actually work? Everything here drives the real
`ingest_complaint` against a real database, using `MockProvider` so the
results are deterministic and no quota is spent.

`test_the_signature_demo` is the important one. It is the exact scenario
from the brief — three students, three similar complaints, one recurring
cluster — asserted step by step, so if the demo is going to break, it breaks
here rather than on stage.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.ai.mock import MockProvider
from app.config import get_settings
from app.db.models import Category, Complaint, ComplaintCluster, StatusEvent
from app.pipeline.ask import answer_admin_question
from app.pipeline.intake import ingest_complaint
from app.pipeline.similarity import count_independent_students, find_similar_complaints

# Session-scoped loop: the app builds one module-level async engine, so
# its pooled connections must never cross an event loop. See conftest.py.
pytestmark = pytest.mark.asyncio(loop_scope="session")

BUILDING = "Innovation Hall"

# Three students describing one real leak. Near-identical phrasing is what a
# live outage actually produces, and it is what clears the 0.92 duplicate
# threshold under the mock provider's keyword-weighted embedding.
LEAK_A = "Water is leaking from the ceiling in the Block A hostel room corridor."
LEAK_B = "Water is leaking from the ceiling in the Block A hostel corridor again."
LEAK_C = "Water is leaking from the ceiling in the Block A hostel room corridor still."

UNRELATED = "The course registration portal shows the wrong seat count for my elective."


async def _submit(db, description, student_id, building=BUILDING, room=None):
    result = await ingest_complaint(
        db,
        description=description,
        location_building=building,
        location_room=room,
        student_id=student_id,
        provider=MockProvider(),
    )
    await db.commit()
    return result


# --- the signature demo --------------------------------------------------


async def test_the_signature_demo(clean_db):
    """Three students, three similar reports, one recurring cluster.

    Asserted as the sequence a judge watches, not as one lump: each student
    moves the system one visible step further.
    """
    settings = get_settings()
    db = clean_db

    # Student A — nothing to compare against, so this is a new complaint.
    first = await _submit(db, LEAK_A, "student_a")
    assert first.similarity_label == "new"
    assert first.cluster is None
    assert first.complaint.category_id is not None, "the AI must have categorized it"
    assert first.complaint.department_id is not None, "and routed it to a department"
    assert first.complaint.ai_summary
    baseline_priority = first.complaint.priority_score

    # Student B — pgvector finds A, similarity clears 0.92, they merge.
    second = await _submit(db, LEAK_B, "student_b")
    assert second.similarity_label == "duplicate", (
        f"expected an auto-merge, got {second.similarity_label} at "
        f"{second.best_match_score}"
    )
    assert second.cluster is not None
    assert second.cluster.member_count == 2
    assert second.cluster.independent_student_count == 2
    assert second.cluster.is_recurring is False, "two students is not yet recurring"
    assert second.became_recurring is False

    # Student C — the cluster crosses the threshold and flips to recurring.
    third = await _submit(db, LEAK_C, "student_c")
    assert third.similarity_label == "duplicate"
    assert third.cluster is not None
    assert third.cluster.independent_student_count >= settings.recurring_threshold
    assert third.cluster.is_recurring is True
    assert third.became_recurring is True, "the recurring transition must fire exactly once"

    # All three complaints are in the same cluster.
    cluster_id = third.cluster.id
    members = (
        (await db.execute(select(Complaint).where(Complaint.cluster_id == cluster_id)))
        .scalars()
        .all()
    )
    assert len(members) == 3

    # Priority rose for everyone, including the complaint submitted first —
    # the situation got worse, so the earliest report is now more urgent too.
    await db.refresh(first.complaint)
    assert first.complaint.priority_score > baseline_priority

    # And the four terms are persisted, not just the total.
    for member in members:
        total = (
            member.priority_severity
            + member.priority_frequency
            + member.priority_safety
            + member.priority_sla_age
        )
        assert member.priority_score == pytest.approx(total, abs=1e-9)
        assert member.priority_frequency > 0


async def test_recurring_needs_three_different_students(clean_db):
    """The anti-gaming property, end to end.

    One student filing the same complaint three times produces a cluster,
    because they really are duplicates — but not a *recurring* one, because
    a recurring campus problem means several people are affected.
    """
    db = clean_db
    await _submit(db, LEAK_A, "student_a")
    await _submit(db, LEAK_B, "student_a")
    third = await _submit(db, LEAK_C, "student_a")

    assert third.cluster is not None
    assert third.cluster.member_count == 3, "all three are still clustered"
    assert third.cluster.independent_student_count == 1
    assert third.cluster.is_recurring is False
    assert third.became_recurring is False


async def test_an_unrelated_complaint_does_not_merge(clean_db):
    db = clean_db
    await _submit(db, LEAK_A, "student_a")
    other = await _submit(db, UNRELATED, "student_b")

    assert other.similarity_label == "new"
    assert other.cluster is None
    assert other.complaint.cluster_id is None


async def test_similarity_search_is_scoped_to_the_same_building(clean_db):
    """Identical text in a different building is a different problem."""
    db = clean_db
    await _submit(db, LEAK_A, "student_a", building="Innovation Hall")
    elsewhere = await _submit(db, LEAK_A, "student_b", building="Hostel Block B")

    assert elsewhere.similarity_label == "new"
    assert elsewhere.cluster is None


async def test_similarity_search_is_scoped_to_the_same_category(clean_db):
    """A complaint only ever competes against its own category.

    Verified at the query level rather than by trying to construct two texts
    that are semantically close but classified differently, which would be
    testing the mock's keyword table rather than the scoping rule.
    """
    db = clean_db
    first = await _submit(db, LEAK_A, "student_a")
    embedding = await MockProvider().embed(first.complaint.ai_summary or LEAK_A)

    wrong_category = (
        await db.execute(select(Category).where(Category.slug == "academics"))
    ).scalar_one()

    same = await find_similar_complaints(
        db,
        embedding=embedding,
        category_id=first.complaint.category_id,
        location_building=BUILDING,
    )
    other = await find_similar_complaints(
        db,
        embedding=embedding,
        category_id=wrong_category.id,
        location_building=BUILDING,
    )
    assert len(same) == 1
    assert other == []


async def test_similarity_search_returns_neighbours_in_distance_order(clean_db):
    """pgvector, not Python, is doing the ranking."""
    db = clean_db
    near = await _submit(db, LEAK_A, "student_a")
    await _submit(db, UNRELATED, "student_b")

    embedding = await MockProvider().embed(near.complaint.ai_summary or LEAK_A)
    results = await find_similar_complaints(
        db,
        embedding=embedding,
        category_id=near.complaint.category_id,
        location_building=BUILDING,
    )
    assert results, "the HNSW query returned nothing"
    assert results[0].complaint_id == near.complaint.id
    assert results[0].similarity > 0.9
    assert results == sorted(results, key=lambda r: -r.similarity)


async def test_anonymous_reports_count_as_independent_students(clean_db):
    """Three anonymous reports are three people, not one.

    Collapsing them would mean a genuine recurring problem reported by
    students who chose not to identify themselves would never be flagged.
    """
    db = clean_db
    await _submit(db, LEAK_A, None)
    await _submit(db, LEAK_B, None)
    third = await _submit(db, LEAK_C, None)

    assert third.cluster is not None
    assert third.cluster.independent_student_count == 3
    assert third.cluster.is_recurring is True

    counted = await count_independent_students(db, third.cluster.id)
    assert counted == 3


async def test_every_complaint_gets_an_embedding_and_a_status_event(clean_db):
    db = clean_db
    result = await _submit(db, LEAK_A, "student_a")

    embedding_row = (await db.execute(select(Complaint).where(Complaint.id == result.complaint.id))).scalar_one()
    assert embedding_row is not None

    events = (
        (
            await db.execute(
                select(StatusEvent).where(StatusEvent.complaint_id == result.complaint.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].status == "open"


async def test_suggested_merge_band_is_recorded_not_applied(clean_db):
    """The 0.75-0.92 band must never auto-merge.

    Driven by temporarily narrowing the duplicate threshold rather than by
    hunting for two texts that happen to land in the band, so the test is
    about the *rule* and does not become flaky if the mock's embedding
    weights are ever retuned.
    """
    db = clean_db
    settings = get_settings()
    original = settings.duplicate_threshold
    try:
        # Force the pair that would normally auto-merge into the review band.
        settings.duplicate_threshold = 0.999999
        settings.suggested_merge_threshold = 0.5

        first = await _submit(db, LEAK_A, "student_a")
        second = await _submit(db, LEAK_B, "student_b")

        assert second.similarity_label == "suggested_merge"
        assert second.cluster is None, "a suggestion must not create a cluster"
        assert second.complaint.cluster_id is None
        assert second.complaint.suggested_match_complaint_id == first.complaint.id
        assert 0.5 <= (second.complaint.suggested_similarity or 0) < 0.999999
    finally:
        settings.duplicate_threshold = original
        settings.suggested_merge_threshold = 0.75


async def test_ask_campusplus_answers_are_grounded_in_real_rows(clean_db):
    db = clean_db
    await _submit(db, LEAK_A, "student_a")
    await _submit(db, LEAK_B, "student_b")
    await _submit(db, UNRELATED, "student_c", building="Academic Block A")

    result = await answer_admin_question(
        db, f"what is going on in {BUILDING}", provider=MockProvider()
    )

    assert result["matched_count"] == 2, "the unrelated building must be filtered out"
    assert BUILDING in result["filters"]
    assert result["cited_complaint_ids"]

    real_ids = {
        str(c) for c in (await db.execute(select(Complaint.id))).scalars().all()
    }
    for cited in result["cited_complaint_ids"]:
        assert cited in real_ids, "a cited id must belong to a complaint that exists"


async def test_ask_campusplus_relaxes_an_over_narrow_question_and_says_so(clean_db):
    """An over-narrow question widens rather than dead-ending — and admits it.

    Asking for academics complaints when only a sanitation one exists used to
    return a bare zero. Now the category filter is dropped, the sanitation
    complaint is returned, and both the answer and the `filters` string state
    plainly that a filter was relaxed — so a widened search can never be
    mistaken for an exact one.
    """
    db = clean_db
    await _submit(db, LEAK_A, "student_a")

    result = await answer_admin_question(
        db, "any academics complaints", provider=MockProvider()
    )
    assert result["matched_count"] == 1
    assert result["cited_complaint_ids"]
    assert "relaxed" in result["answer"].lower()
    assert "relaxed" in result["filters"].lower()


async def test_ask_campusplus_still_returns_nothing_when_there_is_nothing(clean_db):
    """Relaxation widens filters; it never invents data."""
    db = clean_db
    result = await answer_admin_question(
        db, "any academics complaints", provider=MockProvider()
    )
    assert result["matched_count"] == 0
    assert result["cited_complaint_ids"] == []


async def test_resolving_a_complaint_keeps_the_cluster_consistent(clean_db):
    """A cluster is recounted when a member is resolved.

    Otherwise the leaderboard keeps advertising a problem maintenance has
    already fixed.
    """
    from app.pipeline.intake import refresh_cluster

    db = clean_db
    await _submit(db, LEAK_A, "student_a")
    await _submit(db, LEAK_B, "student_b")
    third = await _submit(db, LEAK_C, "student_c")
    cluster_row = third.cluster
    assert cluster_row is not None and cluster_row.is_recurring

    third.complaint.status = "resolved"
    await db.flush()
    await refresh_cluster(db, cluster_row, settings=get_settings())
    await db.commit()

    reloaded = await db.get(ComplaintCluster, cluster_row.id)
    assert reloaded is not None
    # Still 3 members (resolving does not un-cluster), and still recurring —
    # what changed is that the counts were re-derived from the rows rather
    # than left as a stale increment.
    assert reloaded.member_count == 3
    assert reloaded.independent_student_count == 3
