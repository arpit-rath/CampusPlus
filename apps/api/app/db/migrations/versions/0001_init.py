"""init: six-table schema, pgvector extension + HNSW index, seed data

Creates the schema described in AGENTS.md's "Data model" section:
departments, categories, complaints, complaint_embeddings,
complaint_clusters, status_events. Also enables the `vector` extension,
adds an HNSW cosine-distance index on `complaint_embeddings.embedding`
(the index type AGENTS.md's similarity/clustering section assumes), and
seeds a starter set of departments + categories so the API is usable
without a separate seed script.

`complaints.cluster_id` and `complaint_clusters.representative_complaint_id`
reference each other, so both tables are created first and the
`complaints.cluster_id` FK is added afterward with a separate
`create_foreign_key` call to break the circular dependency.

Revision ID: 0001
Revises:
Create Date: 2026-09-09
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str]] = None
depends_on: Union[str, Sequence[str]] = None

EMBEDDING_DIM = 768


def upgrade() -> None:
    # --- Extensions ---------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- departments ----------------------------------------------------
    op.create_table(
        "departments",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.UniqueConstraint("name", name="uq_departments_name"),
    )

    # --- categories -------------------------------------------------------
    op.create_table(
        "categories",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column(
            "default_department_id",
            UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
    )

    # --- complaints ---------------------------------------------------
    # `cluster_id` is added as a plain nullable UUID column here; its FK
    # constraint is created below, once complaint_clusters exists.
    op.create_table(
        "complaints",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("student_id", sa.String(255), nullable=True),
        sa.Column("raw_description", sa.Text, nullable=False),
        sa.Column("photo_url", sa.String(2048), nullable=True),
        sa.Column("location_building", sa.String(255), nullable=True),
        sa.Column("location_room", sa.String(64), nullable=True),
        sa.Column(
            "category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "department_id",
            UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("severity", sa.SmallInteger, nullable=True),
        sa.Column("safety_flag", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("priority_score", sa.Float, nullable=True, server_default="0"),
        sa.Column("cluster_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("ai_summary", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved')", name="ck_complaints_status"
        ),
        sa.CheckConstraint(
            "severity IS NULL OR (severity BETWEEN 1 AND 5)",
            name="ck_complaints_severity_range",
        ),
    )
    op.create_index("ix_complaints_status", "complaints", ["status"])
    op.create_index("ix_complaints_category_id", "complaints", ["category_id"])
    op.create_index("ix_complaints_cluster_id", "complaints", ["cluster_id"])
    op.create_index(
        "ix_complaints_category_building",
        "complaints",
        ["category_id", "location_building"],
    )

    # --- complaint_embeddings -------------------------------------------
    op.create_table(
        "complaint_embeddings",
        sa.Column(
            "complaint_id",
            UUID(as_uuid=True),
            sa.ForeignKey("complaints.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
    )
    # HNSW index for cosine-distance similarity search (AGENTS.md's
    # similarity thresholds are expressed as cosine similarity).
    op.execute(
        "CREATE INDEX ix_complaint_embeddings_embedding_hnsw_cosine "
        "ON complaint_embeddings USING hnsw (embedding vector_cosine_ops)"
    )

    # --- complaint_clusters -----------------------------------------------
    op.create_table(
        "complaint_clusters",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("location_building", sa.String(255), nullable=True),
        sa.Column(
            "representative_complaint_id",
            UUID(as_uuid=True),
            sa.ForeignKey("complaints.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("member_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_recurring", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_complaint_clusters_category_building",
        "complaint_clusters",
        ["category_id", "location_building"],
    )

    # Now that complaint_clusters exists, close the circular FK.
    op.create_foreign_key(
        "fk_complaints_cluster_id",
        "complaints",
        "complaint_clusters",
        ["cluster_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- status_events ----------------------------------------------------
    op.create_table(
        "status_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "complaint_id",
            UUID(as_uuid=True),
            sa.ForeignKey("complaints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_status_events_complaint_id", "status_events", ["complaint_id"])

    # --- seed data ----------------------------------------------------
    _seed_departments_and_categories()


def _seed_departments_and_categories() -> None:
    departments_table = sa.table(
        "departments",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("contact_email", sa.String),
    )
    categories_table = sa.table(
        "categories",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("slug", sa.String),
        sa.column("default_department_id", UUID(as_uuid=True)),
    )

    dept_ids = {
        "it_network": uuid.uuid4(),
        "facilities": uuid.uuid4(),
        "sanitation": uuid.uuid4(),
        "academic_affairs": uuid.uuid4(),
        "general_affairs": uuid.uuid4(),
    }

    op.bulk_insert(
        departments_table,
        [
            {
                "id": dept_ids["it_network"],
                "name": "IT & Network",
                "contact_email": "it-support@campus.edu",
            },
            {
                "id": dept_ids["facilities"],
                "name": "Facilities",
                "contact_email": "facilities@campus.edu",
            },
            {
                "id": dept_ids["sanitation"],
                "name": "Sanitation",
                "contact_email": "sanitation@campus.edu",
            },
            {
                "id": dept_ids["academic_affairs"],
                "name": "Academic Affairs",
                "contact_email": "academics@campus.edu",
            },
            {
                "id": dept_ids["general_affairs"],
                "name": "General Affairs",
                "contact_email": "general-affairs@campus.edu",
            },
        ],
    )

    op.bulk_insert(
        categories_table,
        [
            {
                "id": uuid.uuid4(),
                "slug": "wifi",
                "default_department_id": dept_ids["it_network"],
            },
            {
                "id": uuid.uuid4(),
                "slug": "electrical",
                "default_department_id": dept_ids["facilities"],
            },
            {
                "id": uuid.uuid4(),
                "slug": "sanitation",
                "default_department_id": dept_ids["sanitation"],
            },
            {
                "id": uuid.uuid4(),
                "slug": "infrastructure",
                "default_department_id": dept_ids["facilities"],
            },
            {
                "id": uuid.uuid4(),
                "slug": "academics",
                "default_department_id": dept_ids["academic_affairs"],
            },
            {
                "id": uuid.uuid4(),
                "slug": "other",
                "default_department_id": dept_ids["general_affairs"],
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("status_events")
    op.drop_constraint("fk_complaints_cluster_id", "complaints", type_="foreignkey")
    op.drop_table("complaint_clusters")
    op.execute("DROP INDEX IF EXISTS ix_complaint_embeddings_embedding_hnsw_cosine")
    op.drop_table("complaint_embeddings")
    op.drop_table("complaints")
    op.drop_table("categories")
    op.drop_table("departments")
    # Extension left in place intentionally — other DBs on the same
    # cluster / a later migration may still depend on it.
