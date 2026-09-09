"""SQLAlchemy models — the six tables from CLAUDE.md's "Data model" section.

This is the source of truth for column names/types; the Alembic migration
in `app/db/migrations/versions/0001_init.py` must stay in lockstep with it
(hand-kept, not autogenerate-verified, during the hackathon). Track B's
pipeline code and the frontend's `apps/web/src/lib/api.ts` both assume
these exact names — don't rename anything here without updating both.

Notes on a couple of deliberate choices not spelled out in CLAUDE.md:
- All primary keys are `UUID` (server-generated via Postgres's built-in
  `gen_random_uuid()`, available without an extension since PG13) rather
  than integers, since `Complaint.id` is consumed as an opaque string by
  the frontend.
- `complaints.student_id` is nullable with no FK to a users table — there
  is no auth system in this slice (auth is out of scope for this pass; see
  the build plan's Track A description vs. this session's actual assigned
  scope). Student identity for now is just a free-text string the caller
  supplies, defaulting to "anonymous" at the router level.
- `complaints.cluster_id` -> `complaint_clusters.id` and
  `complaint_clusters.representative_complaint_id` -> `complaints.id` are a
  circular FK pair; the migration creates both tables first and adds the
  `complaints.cluster_id` FK constraint afterward to break the cycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

EMBEDDING_DIM = 768


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)

    categories: Mapped[list["Category"]] = relationship(
        back_populates="default_department"
    )
    complaints: Mapped[list["Complaint"]] = relationship(back_populates="department")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Department id={self.id} name={self.name!r}>"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    default_department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )

    default_department: Mapped["Department"] = relationship(back_populates="categories")
    complaints: Mapped[list["Complaint"]] = relationship(back_populates="category")
    clusters: Mapped[list["ComplaintCluster"]] = relationship(back_populates="category")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Category id={self.id} slug={self.slug!r}>"


class Complaint(Base):
    __tablename__ = "complaints"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved')", name="ck_complaints_status"
        ),
        CheckConstraint(
            "severity IS NULL OR (severity BETWEEN 1 AND 5)", name="ck_complaints_severity_range"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    # Text, not String(2048): a photo URL is short, but this column has
    # historically been handed raw base64 data URLs and silently
    # overflowing a varchar during a live demo is not a risk worth taking.
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_building: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_room: Mapped[str | None] = mapped_column(String(64), nullable=True)

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )

    severity: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    safety_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True only when a photo was supplied AND the model judged it to
    # corroborate the text. NULL means "no photo" — the photo-verification
    # badge in the UI distinguishes all three states.
    photo_matches_text: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    priority_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.0)

    # CLAUDE.md: "All four terms get stored per-complaint (not just the
    # final number) so the UI can render a 4-segment breakdown bar instead
    # of an opaque score." These are the already-weighted contributions and
    # sum to priority_score.
    priority_severity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    priority_frequency: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    priority_safety: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    priority_sla_age: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # FK constraint added in the migration after complaint_clusters exists
    # (circular reference — see module docstring).
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # The 0.75-0.92 "suggested merge" band. Points at the *complaint* we
    # think this duplicates rather than at a cluster, because the closest
    # match is very often itself still unclustered — a suggestion has to be
    # expressible before any cluster exists. Recorded, never auto-applied:
    # an admin confirms or dismisses it from the dashboard.
    suggested_match_complaint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    suggested_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Set when an admin manually re-routes a complaint, so a later
    # re-classification never silently undoes a human decision.
    department_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    category: Mapped["Category | None"] = relationship(back_populates="complaints")
    department: Mapped["Department | None"] = relationship(back_populates="complaints")
    cluster: Mapped["ComplaintCluster | None"] = relationship(
        back_populates="members",
        foreign_keys=[cluster_id],
        primaryjoin="Complaint.cluster_id == ComplaintCluster.id",
    )
    embedding: Mapped["ComplaintEmbedding | None"] = relationship(
        back_populates="complaint", uselist=False, cascade="all, delete-orphan"
    )
    status_events: Mapped[list["StatusEvent"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Complaint id={self.id} status={self.status!r}>"


class ComplaintEmbedding(Base):
    __tablename__ = "complaint_embeddings"

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("complaints.id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    complaint: Mapped["Complaint"] = relationship(back_populates="embedding")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ComplaintEmbedding complaint_id={self.complaint_id}>"


class ComplaintCluster(Base):
    __tablename__ = "complaint_clusters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    location_building: Mapped[str | None] = mapped_column(String(255), nullable=True)
    representative_complaint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="SET NULL"), nullable=True
    )
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Distinct `complaints.student_id` values in this cluster. This — not
    # `member_count` — is what `is_recurring` is derived from, so one
    # student submitting the same complaint five times never fakes a
    # recurring campus-wide problem.
    independent_student_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    category: Mapped["Category"] = relationship(back_populates="clusters")
    representative_complaint: Mapped["Complaint | None"] = relationship(
        foreign_keys=[representative_complaint_id]
    )
    members: Mapped[list["Complaint"]] = relationship(
        back_populates="cluster",
        foreign_keys="[Complaint.cluster_id]",
        primaryjoin="ComplaintCluster.id == Complaint.cluster_id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ComplaintCluster id={self.id} member_count={self.member_count}>"


class StatusEvent(Base):
    __tablename__ = "status_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    complaint: Mapped["Complaint"] = relationship(back_populates="status_events")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StatusEvent id={self.id} status={self.status!r}>"
