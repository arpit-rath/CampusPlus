"""Read API for complaint clusters — the recurring-issue leaderboard.

Before this existed the dashboard approximated clusters client-side by
grouping on `(category_slug + location_building)`, which is a different
thing entirely: two genuinely unrelated WiFi problems in the same building
looked like one recurring issue, and one real cluster spanning a renamed
building looked like two. Clusters are a real row in a real table produced
by real cosine similarity — the frontend should read them, not re-derive a
worse version of them.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models import Category, Complaint, ComplaintCluster
from app.routers.complaints import ComplaintRead, _LOAD_OPTS, _to_read_model

router = APIRouter()


class ClusterRead(BaseModel):
    id: uuid.UUID
    category_slug: str | None
    location_building: str | None
    member_count: int
    independent_student_count: int
    is_recurring: bool
    first_seen: datetime
    last_seen: datetime
    representative_complaint_id: uuid.UUID | None
    representative_summary: str | None
    max_priority_score: float
    safety_flag: bool


class ClusterDetail(ClusterRead):
    members: list[ComplaintRead]


async def _to_cluster_read(db: AsyncSession, row: ComplaintCluster) -> ClusterRead:
    members = (
        (await db.execute(select(Complaint).where(Complaint.cluster_id == row.id)))
        .scalars()
        .all()
    )
    representative = next(
        (m for m in members if m.id == row.representative_complaint_id), None
    )
    return ClusterRead(
        id=row.id,
        category_slug=row.category.slug if row.category else None,
        location_building=row.location_building,
        member_count=row.member_count,
        independent_student_count=row.independent_student_count,
        is_recurring=row.is_recurring,
        first_seen=row.first_seen,
        last_seen=row.last_seen,
        representative_complaint_id=row.representative_complaint_id,
        representative_summary=(
            representative.ai_summary if representative else None
        ),
        max_priority_score=max((m.priority_score or 0.0 for m in members), default=0.0),
        safety_flag=any(m.safety_flag for m in members),
    )


@router.get("", response_model=list[ClusterRead])
async def list_clusters(
    recurring_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[ClusterRead]:
    """Clusters ranked by how many independent students they represent."""
    stmt = select(ComplaintCluster).options(selectinload(ComplaintCluster.category))
    if recurring_only:
        stmt = stmt.where(ComplaintCluster.is_recurring.is_(True))
    stmt = stmt.order_by(
        ComplaintCluster.independent_student_count.desc(),
        ComplaintCluster.last_seen.desc(),
    ).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()
    return [await _to_cluster_read(db, row) for row in rows]


@router.get("/{cluster_id}", response_model=ClusterDetail)
async def get_cluster(
    cluster_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> ClusterDetail:
    row = (
        await db.execute(
            select(ComplaintCluster)
            .options(selectinload(ComplaintCluster.category))
            .where(ComplaintCluster.id == cluster_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cluster not found")

    members = (
        (
            await db.execute(
                select(Complaint)
                .options(*_LOAD_OPTS)
                .where(Complaint.cluster_id == cluster_id)
                .order_by(Complaint.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    base = await _to_cluster_read(db, row)
    return ClusterDetail(**base.model_dump(), members=[_to_read_model(m) for m in members])


@router.get("/by-category/summary", response_model=list[dict])
async def cluster_summary_by_category(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Compact per-category rollup, for dashboard summary tiles."""
    stmt = (
        select(
            Category.slug,
            ComplaintCluster.is_recurring,
            ComplaintCluster.independent_student_count,
        )
        .join(Category, ComplaintCluster.category_id == Category.id)
    )
    rows = (await db.execute(stmt)).all()

    summary: dict[str, dict] = {}
    for slug, is_recurring, students in rows:
        entry = summary.setdefault(
            slug, {"category_slug": slug, "clusters": 0, "recurring": 0, "students": 0}
        )
        entry["clusters"] += 1
        entry["recurring"] += 1 if is_recurring else 0
        entry["students"] += students
    return sorted(summary.values(), key=lambda e: -e["recurring"])
