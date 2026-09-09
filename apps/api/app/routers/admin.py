"""Admin endpoints: Ask CampusPluse, routing overrides, merge review, digest.

Every route here sits behind `require_admin` (a no-op only when ADMIN_TOKEN
is unset — see `app/deps.py`), because each one either exposes the whole
complaint corpus or mutates operational state.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import get_db
from app.db.models import Category, Complaint, ComplaintCluster, Department, StatusEvent
from app.deps import require_admin
from app.pipeline import chaos as chaos_generator
from app.pipeline.ask import answer_admin_question
from app.pipeline.intake import ingest_complaint, merge_into_cluster, refresh_cluster
from app.realtime import broadcaster
from app.routers.complaints import ComplaintRead, _LOAD_OPTS, _get_complaint_or_404, _to_read_model

router = APIRouter(dependencies=[Depends(require_admin)])


# --- Ask CampusPluse ----------------------------------------------------


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class AskResponse(BaseModel):
    answer: str
    cited_complaint_ids: list[str]
    filters: str
    """How the question was interpreted, shown alongside the answer so the
    filtering is auditable rather than magic."""
    matched_count: int


@router.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest, db: AsyncSession = Depends(get_db)) -> AskResponse:
    return AskResponse(**await answer_admin_question(db, payload.question))


# --- Routing override ---------------------------------------------------


class RouteOverride(BaseModel):
    department_id: uuid.UUID | None = None
    category_slug: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=2000)
    actor: str | None = Field(default=None, max_length=255)


@router.patch("/complaints/{complaint_id}/route", response_model=ComplaintRead)
async def override_route(
    complaint_id: uuid.UUID,
    payload: RouteOverride,
    db: AsyncSession = Depends(get_db),
) -> ComplaintRead:
    """Re-route a complaint by hand.

    Deterministic category to department mapping handles the clear cases and
    the model handles the ambiguous ones, but neither is ever the final word:
    this is the always-available human override the plan asks for. Setting a
    department explicitly marks the complaint `department_overridden` so no
    later automated pass silently undoes the decision.
    """
    complaint = await _get_complaint_or_404(complaint_id, db)

    if payload.category_slug is not None:
        category = (
            await db.execute(select(Category).where(Category.slug == payload.category_slug))
        ).scalar_one_or_none()
        if category is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Unknown category slug {payload.category_slug!r}",
            )
        complaint.category_id = category.id
        if payload.department_id is None and not complaint.department_overridden:
            complaint.department_id = category.default_department_id

    if payload.department_id is not None:
        department = await db.get(Department, payload.department_id)
        if department is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown department")
        complaint.department_id = department.id
        complaint.department_overridden = True

    db.add(
        StatusEvent(
            complaint_id=complaint.id,
            status=complaint.status,
            note=payload.note or "Routing overridden by admin",
            actor=payload.actor or "admin",
        )
    )
    await db.commit()

    complaint = await _get_complaint_or_404(complaint_id, db)
    read_model = _to_read_model(complaint)
    broadcaster.publish("complaint.updated", {"complaint": read_model.model_dump(mode="json")})
    return read_model


# --- Suggested merges ---------------------------------------------------


class SuggestedMerge(BaseModel):
    complaint: ComplaintRead
    target: ComplaintRead
    similarity: float


@router.get("/suggested-merges", response_model=list[SuggestedMerge])
async def list_suggested_merges(
    limit: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[SuggestedMerge]:
    """The 0.75-0.92 band, waiting on a human.

    These are the pairs the system thought were probably the same problem
    but not confidently enough to merge on its own — exactly the decision
    the plan says must not be automatic.
    """
    stmt = (
        select(Complaint)
        .options(*_LOAD_OPTS)
        .where(Complaint.suggested_match_complaint_id.isnot(None))
        .order_by(Complaint.suggested_similarity.desc())
        .limit(limit)
    )
    pending = (await db.execute(stmt)).scalars().all()

    results: list[SuggestedMerge] = []
    for complaint in pending:
        target = (
            await db.execute(
                select(Complaint)
                .options(*_LOAD_OPTS)
                .where(Complaint.id == complaint.suggested_match_complaint_id)
            )
        ).scalar_one_or_none()
        if target is None:
            continue
        results.append(
            SuggestedMerge(
                complaint=_to_read_model(complaint),
                target=_to_read_model(target),
                similarity=complaint.suggested_similarity or 0.0,
            )
        )
    return results


class MergeDecision(BaseModel):
    accept: bool
    actor: str | None = Field(default=None, max_length=255)


@router.post("/complaints/{complaint_id}/merge", response_model=ComplaintRead)
async def resolve_suggested_merge(
    complaint_id: uuid.UUID,
    payload: MergeDecision,
    db: AsyncSession = Depends(get_db),
) -> ComplaintRead:
    """Accept or dismiss a suggested merge.

    Accepting runs the same merge path as an automatic duplicate, so a
    human-approved merge and a machine-decided one leave identical state.
    """
    complaint = await _get_complaint_or_404(complaint_id, db)
    if complaint.suggested_match_complaint_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This complaint has no pending merge suggestion"
        )

    cluster_row = None
    # Read the score before merging: merge_into_cluster clears the pending
    # suggestion, so capturing it afterwards would always log 0.00.
    similarity = complaint.suggested_similarity or 0.0
    if payload.accept:
        target = await db.get(Complaint, complaint.suggested_match_complaint_id)
        if target is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Suggested match no longer exists")
        cluster_row = await merge_into_cluster(db, complaint=complaint, target=target)
        note = f"Merged into cluster by admin (similarity {similarity:.2f})"
    else:
        complaint.suggested_match_complaint_id = None
        complaint.suggested_similarity = None
        note = "Merge suggestion dismissed by admin"

    db.add(
        StatusEvent(
            complaint_id=complaint.id,
            status=complaint.status,
            note=note,
            actor=payload.actor or "admin",
        )
    )
    await db.commit()

    complaint = await _get_complaint_or_404(complaint_id, db)
    read_model = _to_read_model(complaint)
    broadcaster.publish("complaint.updated", {"complaint": read_model.model_dump(mode="json")})
    if cluster_row is not None:
        broadcaster.publish(
            "cluster.updated",
            {
                "cluster_id": str(cluster_row.id),
                "member_count": cluster_row.member_count,
                "independent_student_count": cluster_row.independent_student_count,
                "is_recurring": cluster_row.is_recurring,
                "location_building": cluster_row.location_building,
            },
        )
    return read_model


@router.post("/complaints/{complaint_id}/unmerge", response_model=ComplaintRead)
async def unmerge_complaint(
    complaint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ComplaintRead:
    """Pull a complaint back out of its cluster.

    The counterpart to auto-merge: automatic clustering is only safe to run
    if a human can undo a wrong one in a click.
    """
    complaint = await _get_complaint_or_404(complaint_id, db)
    cluster_row = complaint.cluster
    if cluster_row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Complaint is not in a cluster")

    complaint.cluster_id = None
    db.add(
        StatusEvent(
            complaint_id=complaint.id,
            status=complaint.status,
            note="Removed from cluster by admin",
            actor="admin",
        )
    )
    await db.flush()
    await refresh_cluster(db, cluster_row, settings=get_settings())
    await db.commit()

    complaint = await _get_complaint_or_404(complaint_id, db)
    read_model = _to_read_model(complaint)
    broadcaster.publish("complaint.updated", {"complaint": read_model.model_dump(mode="json")})
    return read_model


# --- Weekly digest -------------------------------------------------------


class DigestSection(BaseModel):
    label: str
    value: str


class Digest(BaseModel):
    generated_at: datetime
    window_days: int
    total_complaints: int
    resolved_complaints: int
    recurring_clusters: int
    safety_flagged: int
    top_buildings: list[DigestSection]
    top_categories: list[DigestSection]
    headline_issues: list[ComplaintRead]


@router.get("/digest", response_model=Digest)
async def weekly_digest(
    window_days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> Digest:
    """An auto-generated operational summary over the last `window_days`.

    Pure aggregation over real rows — no model call, so it cannot drift from
    what the dashboard shows and costs nothing to render on stage.
    """
    since = datetime.now(timezone.utc) - timedelta(days=window_days)

    complaints = (
        (
            await db.execute(
                select(Complaint)
                .options(*_LOAD_OPTS)
                .where(Complaint.created_at >= since)
                .order_by(Complaint.priority_score.desc())
            )
        )
        .scalars()
        .all()
    )

    recurring = (
        await db.execute(
            select(func.count())
            .select_from(ComplaintCluster)
            .where(
                ComplaintCluster.is_recurring.is_(True),
                ComplaintCluster.last_seen >= since,
            )
        )
    ).scalar_one()

    def _top(key) -> list[DigestSection]:
        tally: dict[str, int] = {}
        for complaint in complaints:
            value = key(complaint)
            if value:
                tally[value] = tally.get(value, 0) + 1
        return [
            DigestSection(label=label, value=str(count))
            for label, count in sorted(tally.items(), key=lambda kv: -kv[1])[:5]
        ]

    return Digest(
        generated_at=datetime.now(timezone.utc),
        window_days=window_days,
        total_complaints=len(complaints),
        resolved_complaints=sum(1 for c in complaints if c.status == "resolved"),
        recurring_clusters=int(recurring or 0),
        safety_flagged=sum(1 for c in complaints if c.safety_flag),
        top_buildings=_top(lambda c: c.location_building),
        top_categories=_top(lambda c: c.category.slug if c.category else None),
        headline_issues=[_to_read_model(c) for c in complaints[:5]],
    )


# --- Chaos button ---------------------------------------------------------


class ChaosRequest(BaseModel):
    count: int = Field(default=6, ge=1, le=25)
    seed: int | None = None


class ChaosResponse(BaseModel):
    submitted: int
    merged: int
    new_clusters_recurring: int


@router.post("/chaos", response_model=ChaosResponse)
async def chaos(
    payload: ChaosRequest, db: AsyncSession = Depends(get_db)
) -> ChaosResponse:
    """Stream a burst of synthetic complaints through the real pipeline.

    A demo device (plan phase 12.6), and deliberately not a fake one: each
    generated complaint runs the same `ingest_complaint` a student submission
    does, so the merges, clusters and priority changes the dashboard shows are
    genuinely produced by the system. Capped at 25 per press.
    """
    complaints = chaos_generator.generate(payload.count, seed=payload.seed)

    merged = 0
    became_recurring = 0
    for synthetic in complaints:
        result = await ingest_complaint(
            db,
            description=synthetic.description,
            location_building=synthetic.location_building,
            location_room=synthetic.location_room,
            student_id=synthetic.student_id,
        )
        await db.commit()

        if result.cluster is not None:
            merged += 1
        if result.became_recurring:
            became_recurring += 1

        complaint = await _get_complaint_or_404(result.complaint.id, db)
        read_model = _to_read_model(complaint)
        broadcaster.publish(
            "complaint.created",
            {
                "complaint": read_model.model_dump(mode="json"),
                "similarity_label": result.similarity_label,
                "best_match_id": str(result.best_match_id) if result.best_match_id else None,
                "best_match_score": result.best_match_score,
            },
        )
        if result.cluster is not None:
            broadcaster.publish(
                "cluster.recurring" if result.became_recurring else "cluster.updated",
                {
                    "cluster_id": str(result.cluster.id),
                    "member_count": result.cluster.member_count,
                    "independent_student_count": result.cluster.independent_student_count,
                    "is_recurring": result.cluster.is_recurring,
                    "location_building": result.cluster.location_building,
                },
            )

    return ChaosResponse(
        submitted=len(complaints),
        merged=merged,
        new_clusters_recurring=became_recurring,
    )


# --- Provider / system status --------------------------------------------


@router.get("/stats", response_model=dict)
async def admin_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """Counts the dashboard header needs, computed in SQL rather than by
    downloading every complaint and counting in the browser."""
    status_rows = (
        await db.execute(select(Complaint.status, func.count()).group_by(Complaint.status))
    ).all()
    clusters = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(ComplaintCluster.is_recurring.is_(True)),
            ).select_from(ComplaintCluster)
        )
    ).one()
    safety = (
        await db.execute(
            select(func.count()).select_from(Complaint).where(Complaint.safety_flag.is_(True))
        )
    ).scalar_one()
    pending_merges = (
        await db.execute(
            select(func.count())
            .select_from(Complaint)
            .where(Complaint.suggested_match_complaint_id.isnot(None))
        )
    ).scalar_one()

    by_status = {row[0]: row[1] for row in status_rows}
    return {
        "open": by_status.get("open", 0),
        "in_progress": by_status.get("in_progress", 0),
        "resolved": by_status.get("resolved", 0),
        "clusters": clusters[0],
        "recurring_clusters": clusters[1],
        "safety_flagged": int(safety or 0),
        "pending_merges": int(pending_merges or 0),
        "realtime_subscribers": broadcaster.subscriber_count,
    }
