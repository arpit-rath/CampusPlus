"""pgvector-backed nearest-neighbour lookup for a new complaint.

`app/pipeline/cluster.py` deliberately knows nothing about databases — it
is pure vector math. This module is the other half: it owns the one query
that turns "here is a 768-dim embedding" into "here are the handful of
existing complaints closest to it", using the HNSW cosine index that
migration 0001 created.

Why this exists at all: the first integration pass compared the new
embedding against *every* embedding in the building by pulling them all
into Python and looping. That works for a demo seeded with 30 rows and
falls over the moment the table is real — and it left the HNSW index
completely unused. Here the ordering and the top-N cut happen in Postgres,
which is what the index is for.

Scoping follows CLAUDE.md exactly: same `category_id`, same
`location_building`, and a rolling window (default 14 days). Resolved
complaints are excluded — merging a live report into something maintenance
already fixed is worse than opening a new one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import Text, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Complaint, ComplaintEmbedding


@dataclass(frozen=True)
class SimilarComplaint:
    """One nearest-neighbour hit, with everything the caller needs to act."""

    complaint_id: uuid.UUID
    student_id: str | None
    cluster_id: uuid.UUID | None
    similarity: float


async def find_similar_complaints(
    db: AsyncSession,
    *,
    embedding: Sequence[float],
    category_id: uuid.UUID | None,
    location_building: str | None,
    exclude_complaint_id: uuid.UUID | None = None,
    embedding_provider: str | None = None,
    window_days: int = 14,
    limit: int = 20,
) -> list[SimilarComplaint]:
    """Nearest existing complaints to `embedding`, closest first.

    Uses pgvector's cosine distance operator (`<=>`), which the
    `ix_complaint_embeddings_embedding_hnsw_cosine` index is built for.
    Cosine *similarity* — what CLAUDE.md's 0.92/0.75 thresholds are
    expressed in — is `1 - distance`, computed here so callers only ever
    deal in similarity.

    Returns an empty list when `category_id` or `location_building` is
    unknown: without both, the scope CLAUDE.md defines does not exist, and
    silently widening it would let a WiFi complaint merge into a plumbing
    one.
    """
    if category_id is None or not location_building:
        return []

    window_start = datetime.now(timezone.utc) - timedelta(days=window_days)
    distance = ComplaintEmbedding.embedding.cosine_distance(list(embedding))

    stmt = (
        select(
            Complaint.id,
            Complaint.student_id,
            Complaint.cluster_id,
            distance.label("distance"),
        )
        .join(ComplaintEmbedding, ComplaintEmbedding.complaint_id == Complaint.id)
        .where(
            Complaint.category_id == category_id,
            Complaint.location_building == location_building,
            Complaint.created_at >= window_start,
            Complaint.status != "resolved",
        )
        .order_by(distance)
        .limit(limit)
    )
    if exclude_complaint_id is not None:
        stmt = stmt.where(Complaint.id != exclude_complaint_id)
    if embedding_provider is not None:
        # Only compare vectors from the same embedding model. Without this a
        # single fallback-to-mock during a Gemini run would leave a complaint
        # that can never match its own duplicates.
        stmt = stmt.where(ComplaintEmbedding.provider == embedding_provider)

    rows = (await db.execute(stmt)).all()
    return [
        SimilarComplaint(
            complaint_id=row.id,
            student_id=row.student_id,
            cluster_id=row.cluster_id,
            similarity=1.0 - float(row.distance),
        )
        for row in rows
    ]


async def count_independent_students(db: AsyncSession, cluster_id: uuid.UUID) -> int:
    """DISTINCT students represented in a cluster.

    This is the number CLAUDE.md's recurring rule is actually about ("a
    cluster crossing 3 independent students"), as opposed to `member_count`,
    which counts submissions. A complaint with no `student_id` is counted as
    its own independent reporter — an anonymous report is still a distinct
    human, and treating every anonymous row as the same person would
    under-count a real recurring problem.
    """
    reporter = func.coalesce(Complaint.student_id, cast(Complaint.id, Text))
    stmt = select(func.count(distinct(reporter))).where(
        Complaint.cluster_id == cluster_id
    )
    return int((await db.execute(stmt)).scalar_one() or 0)
