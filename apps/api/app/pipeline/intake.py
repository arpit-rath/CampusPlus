"""The complaint intelligence pipeline, end to end, against the database.

This is the module the whole product is about. `app/routers/complaints.py`
is a thin HTTP wrapper over `ingest_complaint`; everything that makes
CampusPluse more than a ticket form happens here, in one readable sequence:

    understand (multimodal)
      -> embed the normalized summary
        -> pgvector nearest neighbours, scoped by category + building + window
          -> classify: duplicate / suggested merge / new
            -> join or create a cluster
              -> count INDEPENDENT students, flag recurring
                -> recompute explainable priority for every cluster member
                  -> route to a department
                    -> persist, then publish realtime events

Two decisions worth stating up front, because they are the ones a reader
will want to argue with:

**Cluster size means independent students, not submissions.** CLAUDE.md
writes the frequency term as `log1p(cluster_size)`, and the recurring rule
as "3 independent students". Using two different notions of size for two
adjacent rules would be a trap: one student spamming the same complaint
would inflate priority even though it explicitly must not flip
`is_recurring`. Both now read `independent_student_count`, so the
anti-gaming property holds for the score as well as for the badge.

**A cluster growing rescoreses its existing members.** Priority is a
property of the situation, not of the moment a row was inserted. When a
third student reports the same leak, the first two reports are also now
higher priority, and the dashboard has to show that — it is the visible
half of the live-merge demo.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import AIProvider, get_provider
from app.config import Settings, get_settings
from app.db.models import Category, Complaint, ComplaintCluster, ComplaintEmbedding, StatusEvent
from app.pipeline import cluster as cluster_math
from app.pipeline import priority as priority_math
from app.pipeline.similarity import (
    SimilarComplaint,
    count_independent_students,
    find_similar_complaints,
)


@dataclass
class IngestResult:
    """What `ingest_complaint` did, for the router and the realtime feed."""

    complaint: Complaint
    similarity_label: cluster_math.SimilarityLabel
    best_match_id: uuid.UUID | None
    best_match_score: float | None
    cluster: ComplaintCluster | None
    became_recurring: bool
    """True only on the transition — the moment a cluster crosses the
    threshold. That edge is what the dashboard animates; a cluster that was
    already recurring before this complaint arrived does not re-fire it."""


def _age_hours(created_at: datetime | None) -> float:
    if created_at is None:
        return 0.0
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 3600)


def apply_priority(
    complaint: Complaint, *, cluster_size: int, settings: Settings
) -> priority_math.PriorityResult:
    """Recompute and store all four priority terms on `complaint`.

    Single place that writes the priority columns, so the stored breakdown
    can never drift from the stored total.
    """
    result = priority_math.compute_priority(
        severity=complaint.severity or 1,
        cluster_size=cluster_size,
        safety_flag=complaint.safety_flag,
        age_hours=_age_hours(complaint.created_at),
        cluster_cap=settings.cluster_cap,
        sla_saturation_hours=settings.sla_saturation_hours,
    )
    complaint.priority_score = result.priority_score
    complaint.priority_severity = result.breakdown.severity
    complaint.priority_frequency = result.breakdown.frequency
    complaint.priority_safety = result.breakdown.safety
    complaint.priority_sla_age = result.breakdown.sla_age
    return result


async def refresh_cluster(
    db: AsyncSession, cluster_row: ComplaintCluster, *, settings: Settings
) -> bool:
    """Recount a cluster, re-flag recurring, and rescore every member.

    Returns True if the cluster crossed the recurring threshold on *this*
    call (i.e. it was not recurring before and is now).

    Counting is done with real queries rather than incrementing a counter,
    which means a merge, an unmerge or a deleted complaint all leave the
    cluster consistent without a separate repair path.
    """
    members = (
        (
            await db.execute(
                select(Complaint).where(Complaint.cluster_id == cluster_row.id)
            )
        )
        .scalars()
        .all()
    )

    independent = await count_independent_students(db, cluster_row.id)
    was_recurring = cluster_row.is_recurring

    cluster_row.member_count = len(members)
    cluster_row.independent_student_count = independent
    cluster_row.is_recurring = independent >= settings.recurring_threshold

    if members:
        timestamps = [m.created_at for m in members if m.created_at is not None]
        if timestamps:
            cluster_row.first_seen = min(timestamps)
            cluster_row.last_seen = max(timestamps)
        # The representative is the highest-severity member, falling back to
        # the earliest — that is the report an admin should read first, not
        # whichever one happened to arrive first.
        cluster_row.representative_complaint_id = max(
            members,
            key=lambda m: (m.severity or 0, -(m.created_at or datetime.now(timezone.utc)).timestamp()),
        ).id

    for member in members:
        apply_priority(member, cluster_size=independent, settings=settings)

    return cluster_row.is_recurring and not was_recurring


async def _join_or_create_cluster(
    db: AsyncSession,
    *,
    complaint: Complaint,
    match: SimilarComplaint,
) -> ComplaintCluster | None:
    """Attach `complaint` to the cluster of `match`, creating one if needed."""
    match_complaint = await db.get(Complaint, match.complaint_id)
    if match_complaint is None:
        return None

    if match_complaint.cluster_id is not None:
        cluster_row = await db.get(ComplaintCluster, match_complaint.cluster_id)
        if cluster_row is None:
            return None
    else:
        if match_complaint.category_id is None:
            # complaint_clusters.category_id is NOT NULL; an unclassified
            # match cannot anchor a cluster.
            return None
        cluster_row = ComplaintCluster(
            category_id=match_complaint.category_id,
            location_building=match_complaint.location_building,
            representative_complaint_id=match_complaint.id,
            member_count=1,
            independent_student_count=1,
            is_recurring=False,
            # first_seen/last_seen are NOT NULL with a now() server default.
            # They are set properly by refresh_cluster() below; passing the
            # new complaint's created_at here would write NULL, because a
            # server default is not populated until the row is refreshed.
        )
        db.add(cluster_row)
        await db.flush()
        match_complaint.cluster_id = cluster_row.id

    complaint.cluster_id = cluster_row.id
    return cluster_row


async def ingest_complaint(
    db: AsyncSession,
    *,
    description: str,
    location_building: str,
    location_room: str | None = None,
    student_id: str | None = None,
    photo_url: str | None = None,
    image_bytes: bytes | None = None,
    provider: AIProvider | None = None,
) -> IngestResult:
    """Run the full intake pipeline for one new complaint and persist it.

    The caller is responsible for the surrounding transaction: this function
    flushes but never commits, so a router can commit once and a test can
    roll back.
    """
    settings = get_settings()
    ai = provider or get_provider()

    complaint = Complaint(
        # NULL, not the string "anonymous": every anonymous report is a
        # distinct unknown reporter. Collapsing them all onto one literal id
        # would make three anonymous students look like one, which is
        # exactly the count `is_recurring` depends on.
        student_id=(student_id.strip() or None) if student_id else None,
        raw_description=description,
        photo_url=photo_url,
        location_building=location_building,
        location_room=location_room,
        status="open",
        safety_flag=False,
    )
    db.add(complaint)
    await db.flush()
    # created_at is a server default; without this refresh it is None, and
    # every downstream age/first_seen calculation silently breaks.
    await db.refresh(complaint, ["created_at"])

    # --- 1. multimodal understanding ------------------------------------
    understanding = await ai.understand_complaint(description, image_bytes)

    # --- 2. embed the normalized summary, not the raw text --------------
    embedding = await ai.embed(understanding.summary)

    category_row = (
        await db.execute(select(Category).where(Category.slug == understanding.category))
    ).scalar_one_or_none()

    complaint.category_id = category_row.id if category_row else None
    complaint.department_id = category_row.default_department_id if category_row else None
    complaint.severity = understanding.severity
    complaint.safety_flag = understanding.safety_flag
    complaint.ai_summary = understanding.summary
    complaint.photo_matches_text = (
        understanding.photo_matches_text if image_bytes is not None else None
    )

    db.add(ComplaintEmbedding(complaint_id=complaint.id, embedding=list(embedding)))
    await db.flush()

    # --- 3. similarity search (pgvector, scoped) ------------------------
    neighbours = await find_similar_complaints(
        db,
        embedding=embedding,
        category_id=complaint.category_id,
        location_building=complaint.location_building,
        exclude_complaint_id=complaint.id,
        window_days=settings.similarity_window_days,
        limit=settings.similarity_candidate_limit,
    )

    best = neighbours[0] if neighbours else None
    label: cluster_math.SimilarityLabel = "new"
    cluster_row: ComplaintCluster | None = None

    if best is not None:
        label = cluster_math.classify_similarity(
            best.similarity,
            duplicate_threshold=settings.duplicate_threshold,
            suggested_merge_threshold=settings.suggested_merge_threshold,
        )

        if label == "duplicate":
            # --- 4. auto-merge --------------------------------------------
            cluster_row = await _join_or_create_cluster(db, complaint=complaint, match=best)
        elif label == "suggested_merge":
            # Recorded for an admin, never applied automatically.
            complaint.suggested_match_complaint_id = best.complaint_id
            complaint.suggested_similarity = best.similarity

    await db.flush()

    # --- 5. recurring detection + explainable priority -------------------
    became_recurring = False
    if cluster_row is not None:
        became_recurring = await refresh_cluster(db, cluster_row, settings=settings)
    else:
        apply_priority(complaint, cluster_size=1, settings=settings)

    db.add(
        StatusEvent(
            complaint_id=complaint.id,
            status=complaint.status,
            note="Complaint submitted and analyzed",
            actor=complaint.student_id or "anonymous",
        )
    )
    await db.flush()

    return IngestResult(
        complaint=complaint,
        similarity_label=label,
        best_match_id=best.complaint_id if best else None,
        best_match_score=best.similarity if best else None,
        cluster=cluster_row,
        became_recurring=became_recurring,
    )


async def merge_into_cluster(
    db: AsyncSession, *, complaint: Complaint, target: Complaint
) -> ComplaintCluster | None:
    """Admin-confirmed merge of `complaint` into `target`'s cluster.

    Same code path as an automatic duplicate merge, so a human-approved
    suggestion and a machine-decided duplicate produce identical state —
    there is no second, subtly-different merge implementation to keep in
    sync.
    """
    settings = get_settings()
    cluster_row = await _join_or_create_cluster(
        db,
        complaint=complaint,
        match=SimilarComplaint(
            complaint_id=target.id,
            student_id=target.student_id,
            cluster_id=target.cluster_id,
            similarity=1.0,
        ),
    )
    complaint.suggested_match_complaint_id = None
    complaint.suggested_similarity = None
    await db.flush()

    if cluster_row is not None:
        await refresh_cluster(db, cluster_row, settings=settings)
    return cluster_row
