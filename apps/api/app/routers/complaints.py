"""HTTP surface for complaints.

Thin on purpose: the intelligence lives in `app/pipeline/intake.py`, and
this module's job is to validate input, call it, publish a realtime event,
and serialize the result into the shape `apps/web/src/lib/api.ts` expects.

One serialization note that matters. The stored `priority_*` columns are the
source of truth for the four breakdown segments, but the SLA-age term keeps
climbing while a complaint sits open and nothing recomputes it between
writes. `_to_read_model` therefore refreshes just that one term at read time
and adjusts the total to match, so an admin watching the dashboard sees an
ageing complaint actually rise. The other three terms are read straight from
the database — they only change when something real changes (a merge, a
re-classification), and those paths already write them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.database import get_db
from app.db.models import Complaint, StatusEvent
from app.deps import require_admin
from app.pipeline import priority as priority_math
from app.pipeline.intake import ingest_complaint, refresh_cluster
from app.realtime import broadcaster
from app.storage import InvalidPhotoError, decode_photo, save_photo

router = APIRouter()


# --- Schemas -------------------------------------------------------------


class ComplaintStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"


class PriorityBreakdown(BaseModel):
    """Mirrors apps/web/src/lib/api.ts's PriorityBreakdown.

    Each field is the already-weighted contribution of one term, so the four
    sum to `priority_score` and each is directly usable as one segment width
    in the 4-segment bar.
    """

    severity: float = 0.0
    frequency: float = 0.0
    safety: float = 0.0
    sla_age: float = 0.0


class ComplaintCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=5000)
    location_building: str = Field(..., min_length=1, max_length=255)
    location_room: str | None = Field(default=None, max_length=64)
    photo_base64: str | None = None
    # Free-text reporter identity. Optional: leave it out and the complaint
    # is anonymous, which counts as a distinct reporter rather than being
    # lumped in with every other anonymous report.
    student_id: str | None = Field(default=None, max_length=255)


class ComplaintStatusUpdate(BaseModel):
    status: ComplaintStatus
    note: str | None = Field(default=None, max_length=2000)
    actor: str | None = Field(default=None, max_length=255)


class ComplaintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: str | None
    raw_description: str
    photo_url: str | None
    photo_matches_text: bool | None
    location_building: str | None
    location_room: str | None
    category_slug: str | None
    department_id: uuid.UUID | None
    department_name: str | None
    severity: int | None
    safety_flag: bool
    priority_score: float
    priority_breakdown: PriorityBreakdown
    status: ComplaintStatus
    ai_summary: str | None
    cluster_id: uuid.UUID | None
    is_recurring: bool
    cluster_member_count: int
    independent_student_count: int
    suggested_match_complaint_id: uuid.UUID | None
    suggested_similarity: float | None
    department_overridden: bool
    created_at: datetime


class StatusEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ComplaintStatus
    note: str | None
    actor: str | None
    created_at: datetime


# Eager-load every relation `_to_read_model` touches — async SQLAlchemy
# cannot lazy-load once the session context has ended.
_LOAD_OPTS = (
    selectinload(Complaint.category),
    selectinload(Complaint.department),
    selectinload(Complaint.cluster),
)


def _age_hours(created_at: datetime | None) -> float:
    if created_at is None:
        return 0.0
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 3600)


def _to_read_model(complaint: Complaint) -> ComplaintRead:
    settings = get_settings()

    # Only the SLA term is time-dependent; refresh it at read time so an
    # ageing complaint visibly climbs without a background job.
    sla_term = priority_math.SLA_AGE_WEIGHT * priority_math.sla_age_factor(
        _age_hours(complaint.created_at), settings.sla_saturation_hours
    )
    breakdown = PriorityBreakdown(
        severity=complaint.priority_severity or 0.0,
        frequency=complaint.priority_frequency or 0.0,
        safety=complaint.priority_safety or 0.0,
        sla_age=sla_term,
    )
    total = breakdown.severity + breakdown.frequency + breakdown.safety + breakdown.sla_age

    cluster = complaint.cluster
    return ComplaintRead(
        id=complaint.id,
        student_id=complaint.student_id,
        raw_description=complaint.raw_description,
        photo_url=complaint.photo_url,
        photo_matches_text=complaint.photo_matches_text,
        location_building=complaint.location_building,
        location_room=complaint.location_room,
        category_slug=complaint.category.slug if complaint.category else None,
        department_id=complaint.department_id,
        department_name=complaint.department.name if complaint.department else None,
        severity=complaint.severity,
        safety_flag=complaint.safety_flag,
        priority_score=total,
        priority_breakdown=breakdown,
        status=ComplaintStatus(complaint.status),
        ai_summary=complaint.ai_summary,
        cluster_id=complaint.cluster_id,
        is_recurring=bool(cluster and cluster.is_recurring),
        cluster_member_count=cluster.member_count if cluster else 1,
        independent_student_count=cluster.independent_student_count if cluster else 1,
        suggested_match_complaint_id=complaint.suggested_match_complaint_id,
        suggested_similarity=complaint.suggested_similarity,
        department_overridden=complaint.department_overridden,
        created_at=complaint.created_at,
    )


async def _get_complaint_or_404(complaint_id: uuid.UUID, db: AsyncSession) -> Complaint:
    # `populate_existing` matters here, and its absence was a real bug. The
    # session is configured with `expire_on_commit=False`, so after a write
    # the identity map still holds the object with its previously-loaded
    # relationships — and SQLAlchemy will not overwrite already-loaded
    # attributes on a re-query without being told to. Re-reading a complaint
    # straight after re-routing it therefore returned the *old* department.
    # Every mutating route re-reads through this function, so forcing a
    # refresh here fixes the whole class of staleness at once.
    stmt = (
        select(Complaint)
        .options(*_LOAD_OPTS)
        .where(Complaint.id == complaint_id)
        .execution_options(populate_existing=True)
    )
    complaint = (await db.execute(stmt)).scalar_one_or_none()
    if complaint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complaint not found")
    return complaint


# --- Routes ----------------------------------------------------------


@router.get("", response_model=list[ComplaintRead])
async def list_complaints(
    status_filter: ComplaintStatus | None = Query(default=None, alias="status"),
    category: str | None = Query(default=None, max_length=64),
    building: str | None = Query(default=None, max_length=255),
    recurring_only: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[ComplaintRead]:
    """Priority-sorted complaint list, with the filters the dashboard needs.

    Filtering happens in SQL rather than in the browser so the dashboard
    stays responsive as the table grows, and so "Ask CampusPlus" and the
    dashboard agree on what a filter means.
    """
    stmt = select(Complaint).options(*_LOAD_OPTS)
    if status_filter is not None:
        stmt = stmt.where(Complaint.status == status_filter.value)
    if category:
        from app.db.models import Category

        stmt = stmt.join(Category, Complaint.category_id == Category.id).where(
            Category.slug == category
        )
    if building:
        stmt = stmt.where(Complaint.location_building == building)
    if recurring_only:
        from app.db.models import ComplaintCluster

        stmt = stmt.join(
            ComplaintCluster, Complaint.cluster_id == ComplaintCluster.id
        ).where(ComplaintCluster.is_recurring.is_(True))

    stmt = stmt.order_by(Complaint.priority_score.desc(), Complaint.created_at.desc()).limit(
        limit
    )
    complaints = (await db.execute(stmt)).scalars().all()
    return [_to_read_model(c) for c in complaints]


@router.get("/{complaint_id}", response_model=ComplaintRead)
async def get_complaint(
    complaint_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> ComplaintRead:
    return _to_read_model(await _get_complaint_or_404(complaint_id, db))


@router.get("/{complaint_id}/events", response_model=list[StatusEventRead])
async def list_status_events(
    complaint_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[StatusEvent]:
    """Audit trail for one complaint, oldest first — the student's timeline."""
    await _get_complaint_or_404(complaint_id, db)
    stmt = (
        select(StatusEvent)
        .where(StatusEvent.complaint_id == complaint_id)
        .order_by(StatusEvent.created_at.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


@router.post("", response_model=ComplaintRead, status_code=status.HTTP_201_CREATED)
async def create_complaint(
    payload: ComplaintCreate, db: AsyncSession = Depends(get_db)
) -> ComplaintRead:
    """Submit a complaint and run the full intelligence pipeline on it."""
    try:
        decoded = decode_photo(payload.photo_base64)
    except InvalidPhotoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    image_bytes: bytes | None = None
    photo_url: str | None = None
    if decoded is not None:
        image_bytes, extension, _mime = decoded
        photo_url = save_photo(image_bytes, extension)

    result = await ingest_complaint(
        db,
        description=payload.description,
        location_building=payload.location_building,
        location_room=payload.location_room,
        student_id=payload.student_id,
        photo_url=photo_url,
        image_bytes=image_bytes,
    )
    await db.commit()

    complaint = await _get_complaint_or_404(result.complaint.id, db)
    read_model = _to_read_model(complaint)

    # --- realtime ---------------------------------------------------------
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
    return read_model


@router.patch(
    "/{complaint_id}/status",
    response_model=ComplaintRead,
    dependencies=[Depends(require_admin)],
)
async def update_complaint_status(
    complaint_id: uuid.UUID,
    payload: ComplaintStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> ComplaintRead:
    """Admin status transition. Appends a `status_events` row for the audit trail."""
    complaint = await _get_complaint_or_404(complaint_id, db)

    complaint.status = payload.status.value
    db.add(
        StatusEvent(
            complaint_id=complaint.id,
            status=payload.status.value,
            note=payload.note,
            actor=payload.actor or "admin",
        )
    )
    # Resolving a complaint shrinks its cluster's live footprint, and
    # `find_similar_complaints` excludes resolved rows — so the cluster has
    # to be recounted or the leaderboard keeps advertising fixed problems.
    if complaint.cluster is not None:
        await refresh_cluster(db, complaint.cluster, settings=get_settings())

    await db.commit()

    complaint = await _get_complaint_or_404(complaint.id, db)
    read_model = _to_read_model(complaint)
    broadcaster.publish("complaint.updated", {"complaint": read_model.model_dump(mode="json")})
    return read_model


@router.delete(
    "/{complaint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(require_admin)],
)
async def delete_complaint(
    complaint_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    complaint = await _get_complaint_or_404(complaint_id, db)

    cluster = complaint.cluster
    await db.delete(complaint)
    await db.flush()
    if cluster is not None:
        await refresh_cluster(db, cluster, settings=get_settings())
    await db.commit()

    broadcaster.publish("complaint.updated", {"deleted_id": str(complaint_id)})
