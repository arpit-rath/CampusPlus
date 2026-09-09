"""CRUD + AI-pipeline-integrated router for `complaints`.

This is Track A's original CRUD skeleton with the intelligence pipeline
wired in at integration time: `POST /complaints` now calls
`app.pipeline.understand.process_new_complaint` (Track B), assigns a
category/department from the returned understanding, joins-or-creates a
`complaint_clusters` row when the pipeline says "duplicate", and persists
the embedding. `priority_score`/`priority_breakdown` are recomputed live on
every read (see `_to_read_model`) rather than frozen at create time, so the
SLA-age term keeps rising the longer a complaint sits open — a nice side
effect of CLAUDE.md's formula being cheap and pure, not extra work.

`GET /complaints` (list) and `GET /complaints/{id}` return the shape
`apps/web/src/lib/api.ts`'s `Complaint` type expects.
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.schemas import CATEGORY_SLUGS
from app.config import get_settings
from app.db.database import get_db
from app.db.models import Category, Complaint, ComplaintCluster, ComplaintEmbedding, StatusEvent
from app.pipeline import priority as priority_pipeline
from app.pipeline.understand import process_new_complaint

router = APIRouter()


# --- Schemas -------------------------------------------------------------


class ComplaintStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"


class PriorityBreakdown(BaseModel):
    """Mirrors apps/web/src/lib/api.ts's PriorityBreakdown."""

    severity: float = 0.0
    frequency: float = 0.0
    safety: float = 0.0
    sla_age: float = 0.0


class ComplaintCreate(BaseModel):
    """Mirrors apps/web/src/lib/api.ts's CreateComplaintInput.

    `student_id` is intentionally *not* in that frontend type (no auth in
    this slice) — optional here, defaults to "anonymous".
    """

    description: str = Field(..., min_length=1)
    location_building: str = Field(..., min_length=1, max_length=255)
    location_room: str | None = Field(default=None, max_length=64)
    photo_base64: str | None = None
    student_id: str | None = Field(default=None, max_length=255)


class ComplaintStatusUpdate(BaseModel):
    status: ComplaintStatus
    note: str | None = None
    actor: str | None = None


class ComplaintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    raw_description: str
    photo_url: str | None
    location_building: str | None
    location_room: str | None
    category_slug: str | None
    department_name: str | None
    severity: int | None
    safety_flag: bool
    priority_score: float
    priority_breakdown: PriorityBreakdown
    status: ComplaintStatus
    ai_summary: str | None
    is_recurring: bool
    cluster_member_count: int
    created_at: datetime


# Eager-load every relation `_to_read_model` touches — async SQLAlchemy
# can't lazy-load after the session context ends.
_LOAD_OPTS = (
    selectinload(Complaint.category),
    selectinload(Complaint.department),
    selectinload(Complaint.cluster),
)


def _age_hours(created_at: datetime) -> float:
    now = datetime.now(timezone.utc)
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - created).total_seconds() / 3600)


def _to_read_model(complaint: Complaint) -> ComplaintRead:
    cluster_size = complaint.cluster.member_count if complaint.cluster else 1
    result = priority_pipeline.compute_priority(
        severity=complaint.severity or 1,
        cluster_size=cluster_size,
        safety_flag=complaint.safety_flag,
        age_hours=_age_hours(complaint.created_at),
    )

    return ComplaintRead(
        id=complaint.id,
        raw_description=complaint.raw_description,
        photo_url=complaint.photo_url,
        location_building=complaint.location_building,
        location_room=complaint.location_room,
        category_slug=complaint.category.slug if complaint.category else None,
        department_name=complaint.department.name if complaint.department else None,
        severity=complaint.severity,
        safety_flag=complaint.safety_flag,
        priority_score=result.priority_score,
        priority_breakdown=PriorityBreakdown(**result.breakdown.as_dict()),
        status=ComplaintStatus(complaint.status),
        ai_summary=complaint.ai_summary,
        is_recurring=bool(complaint.cluster and complaint.cluster.is_recurring),
        cluster_member_count=complaint.cluster.member_count if complaint.cluster else 0,
        created_at=complaint.created_at,
    )


async def _get_complaint_or_404(complaint_id: uuid.UUID, db: AsyncSession) -> Complaint:
    stmt = select(Complaint).options(*_LOAD_OPTS).where(Complaint.id == complaint_id)
    result = await db.execute(stmt)
    complaint = result.scalar_one_or_none()
    if complaint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complaint not found")
    return complaint


def _decode_photo_bytes(photo_base64: str | None) -> bytes | None:
    """Best-effort decode of a (possibly data-URL-prefixed) base64 photo.

    Returns None on anything malformed rather than raising — a bad photo
    payload shouldn't block understanding the text description.
    """
    if not photo_base64:
        return None
    raw = photo_base64.split(",", 1)[1] if "," in photo_base64 else photo_base64
    try:
        return base64.b64decode(raw)
    except Exception:
        return None


async def _candidate_embeddings(
    db: AsyncSession, location_building: str
) -> list[tuple[str, list[float]]]:
    """Existing embeddings to compare a new complaint against.

    Scoped per CLAUDE.md: same building + rolling 14-day window. Category
    scoping is deliberately skipped here (see app/pipeline/understand.py's
    module docstring) — the AI-derived category isn't known until *after*
    this query runs.
    """
    window_start = datetime.now(timezone.utc) - timedelta(days=14)
    stmt = (
        select(Complaint.id, ComplaintEmbedding.embedding)
        .join(ComplaintEmbedding, ComplaintEmbedding.complaint_id == Complaint.id)
        .where(
            Complaint.location_building == location_building,
            Complaint.created_at >= window_start,
        )
    )
    rows = (await db.execute(stmt)).all()
    return [(str(cid), list(embedding)) for cid, embedding in rows]


async def _assign_cluster(
    db: AsyncSession,
    *,
    new_complaint: Complaint,
    category: Category | None,
    similarity: dict,
) -> ComplaintCluster | None:
    """Join an existing cluster or start a new one when the pipeline found a duplicate.

    Only "duplicate" (>=0.92 cosine, per CLAUDE.md) auto-merges. A
    "suggested_merge" (0.75-0.92) is intentionally left unclustered here —
    that's meant to be surfaced to an admin for a one-click merge, which is
    a frontend feature not built in this pass (flagged as a stretch goal).
    """
    if similarity.get("label") != "duplicate" or similarity.get("best_match_id") is None:
        return None

    match_id = uuid.UUID(similarity["best_match_id"])
    match_complaint = await db.get(Complaint, match_id)
    if match_complaint is None:
        return None

    settings = get_settings()

    if match_complaint.cluster_id is not None:
        cluster_row = await db.get(ComplaintCluster, match_complaint.cluster_id)
        if cluster_row is None:
            return None
        cluster_row.member_count += 1
        cluster_row.last_seen = new_complaint.created_at
        if cluster_row.member_count >= settings.recurring_threshold:
            cluster_row.is_recurring = True
        return cluster_row

    cluster_row = ComplaintCluster(
        category_id=(category.id if category else match_complaint.category_id),
        location_building=new_complaint.location_building,
        representative_complaint_id=match_complaint.id,
        member_count=2,
        is_recurring=2 >= settings.recurring_threshold,
    )
    db.add(cluster_row)
    await db.flush()
    match_complaint.cluster_id = cluster_row.id
    return cluster_row


# --- Routes ----------------------------------------------------------


@router.get("", response_model=list[ComplaintRead])
async def list_complaints(
    status_filter: ComplaintStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[ComplaintRead]:
    stmt = select(Complaint).options(*_LOAD_OPTS).order_by(Complaint.created_at.desc())
    if status_filter is not None:
        stmt = stmt.where(Complaint.status == status_filter.value)

    result = await db.execute(stmt)
    complaints = result.scalars().all()
    return [_to_read_model(c) for c in complaints]


@router.get("/{complaint_id}", response_model=ComplaintRead)
async def get_complaint(
    complaint_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> ComplaintRead:
    complaint = await _get_complaint_or_404(complaint_id, db)
    return _to_read_model(complaint)


@router.post("", response_model=ComplaintRead, status_code=status.HTTP_201_CREATED)
async def create_complaint(
    payload: ComplaintCreate, db: AsyncSession = Depends(get_db)
) -> ComplaintRead:
    # Photo storage (bucket/CDN upload) is out of scope for this scaffold —
    # kept verbatim as photo_url so the field round-trips end to end.
    photo_url = payload.photo_base64 or None

    complaint = Complaint(
        student_id=payload.student_id or "anonymous",
        raw_description=payload.description,
        photo_url=photo_url,
        location_building=payload.location_building,
        location_room=payload.location_room,
        category_id=None,
        department_id=None,
        severity=None,
        safety_flag=False,
        priority_score=0.0,
        status=ComplaintStatus.open.value,
    )
    db.add(complaint)
    await db.flush()  # populate complaint.id (server-generated UUID) + created_at default

    # --- AI pipeline: understand + embed + similarity + priority --------
    candidates = await _candidate_embeddings(db, payload.location_building)
    pipeline_result = await process_new_complaint(
        description=payload.description,
        image_bytes=_decode_photo_bytes(payload.photo_base64),
        existing_embeddings=candidates,
    )
    understanding = pipeline_result["understanding"]
    similarity = pipeline_result["similarity"]

    category_row: Category | None = None
    if understanding.get("category") in CATEGORY_SLUGS:
        category_row = (
            await db.execute(select(Category).where(Category.slug == understanding["category"]))
        ).scalar_one_or_none()

    cluster_row = await _assign_cluster(
        db, new_complaint=complaint, category=category_row, similarity=similarity
    )

    complaint.category_id = category_row.id if category_row else None
    complaint.department_id = category_row.default_department_id if category_row else None
    complaint.severity = understanding.get("severity")
    complaint.safety_flag = bool(understanding.get("safety_flag"))
    complaint.ai_summary = understanding.get("summary")
    if cluster_row is not None:
        complaint.cluster_id = cluster_row.id
        complaint.priority_score = priority_pipeline.compute_priority(
            severity=complaint.severity or 1,
            cluster_size=cluster_row.member_count,
            safety_flag=complaint.safety_flag,
            age_hours=0.0,
        ).priority_score
    else:
        complaint.priority_score = pipeline_result["priority"]["priority_score"]

    db.add(
        ComplaintEmbedding(complaint_id=complaint.id, embedding=pipeline_result["embedding"])
    )
    db.add(
        StatusEvent(
            complaint_id=complaint.id,
            status=complaint.status,
            note="Complaint submitted",
            actor=complaint.student_id,
        )
    )

    await db.commit()
    complaint = await _get_complaint_or_404(complaint.id, db)
    return _to_read_model(complaint)


@router.patch("/{complaint_id}/status", response_model=ComplaintRead)
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
            actor=payload.actor,
        )
    )
    await db.commit()

    complaint = await _get_complaint_or_404(complaint.id, db)
    return _to_read_model(complaint)


@router.delete("/{complaint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_complaint(
    complaint_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    complaint = await db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complaint not found")
    await db.delete(complaint)
    await db.commit()
