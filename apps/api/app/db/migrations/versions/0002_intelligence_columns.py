"""intelligence columns: stored priority breakdown, photo verification,
suggested merges, independent-student counts

Everything here backs a behaviour the implementation plan asks for that the
initial schema had no column for:

- `complaints.priority_*` — AGENTS.md is explicit that "all four terms get
  stored per-complaint (not just the final number) so the UI can render a
  4-segment breakdown bar". They were being recomputed on every read and
  never persisted, which meant nothing could sort or filter on a single
  term server-side.
- `complaints.photo_matches_text` — the AI schema has produced this field
  since day one and the router threw it away. It is the photo-verification
  badge (plan phase 12.3). Nullable on purpose: NULL = no photo was
  attached, which is different from "a photo was attached and did not
  match".
- `complaints.suggested_match_complaint_id` / `suggested_similarity` —
  the 0.75-0.92 band. Previously computed and discarded, so the
  "suggested merge, surfaced to an admin, not auto-applied" rule had
  nowhere to live. It references a complaint rather than a cluster because
  the nearest match is usually still unclustered itself.
- `complaints.department_overridden` — records that a human re-routed this
  complaint, so automated re-classification never silently reverses them.
- `complaint_clusters.independent_student_count` — `is_recurring` was
  derived from `member_count`, so three submissions from one student
  falsely marked a cluster recurring. This column counts DISTINCT
  `student_id` and is what the recurring threshold now reads.

Backfill: existing rows get their priority breakdown recomputed from the
stored severity/safety/cluster size using the same weights as
`app/pipeline/priority.py`, expressed in SQL so the migration does not
import application code (which would couple schema history to whatever the
formula happens to be later). `independent_student_count` is backfilled
with a real DISTINCT count and `is_recurring` is re-derived from it, which
also repairs any cluster that was wrongly flagged under the old rule.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str]] = None
depends_on: Union[str, Sequence[str]] = None

# Kept in sync with app/pipeline/priority.py. Duplicated here on purpose:
# a migration must describe the world as it was at this revision, not
# import a module that will keep changing underneath it.
SEVERITY_WEIGHT = 0.40
FREQUENCY_WEIGHT = 0.30
SAFETY_WEIGHT = 0.20
CLUSTER_CAP = 20


def upgrade() -> None:
    # --- complaints -----------------------------------------------------
    op.add_column("complaints", sa.Column("photo_matches_text", sa.Boolean(), nullable=True))
    op.add_column(
        "complaints",
        sa.Column("priority_severity", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "complaints",
        sa.Column("priority_frequency", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "complaints",
        sa.Column("priority_safety", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "complaints",
        sa.Column("priority_sla_age", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "complaints",
        sa.Column("suggested_match_complaint_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column("complaints", sa.Column("suggested_similarity", sa.Float(), nullable=True))
    op.add_column(
        "complaints",
        sa.Column(
            "department_overridden", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_foreign_key(
        "fk_complaints_suggested_match_complaint_id",
        "complaints",
        "complaints",
        ["suggested_match_complaint_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # A raw base64 data URL never fit in varchar(2048); widen so a bad
    # payload fails validation rather than truncating in the database.
    op.alter_column(
        "complaints",
        "photo_url",
        existing_type=sa.String(2048),
        type_=sa.Text(),
        existing_nullable=True,
    )

    # --- complaint_clusters ---------------------------------------------
    op.add_column(
        "complaint_clusters",
        sa.Column(
            "independent_student_count", sa.Integer(), nullable=False, server_default="1"
        ),
    )

    # --- backfill --------------------------------------------------------
    op.execute(
        f"""
        UPDATE complaints c
        SET priority_severity = {SEVERITY_WEIGHT} * (GREATEST(1, LEAST(5, COALESCE(c.severity, 1))) - 1) / 4.0,
            priority_frequency = {FREQUENCY_WEIGHT} * LEAST(
                1.0,
                ln(1 + COALESCE(cl.member_count, 1)) / ln(1 + {CLUSTER_CAP})
            ),
            priority_safety = {SAFETY_WEIGHT} * (CASE WHEN c.safety_flag THEN 1 ELSE 0 END)
        FROM (SELECT id, member_count FROM complaint_clusters) cl
        WHERE c.cluster_id = cl.id
        """
    )
    op.execute(
        f"""
        UPDATE complaints c
        SET priority_severity = {SEVERITY_WEIGHT} * (GREATEST(1, LEAST(5, COALESCE(c.severity, 1))) - 1) / 4.0,
            priority_frequency = {FREQUENCY_WEIGHT} * (ln(2.0) / ln(1 + {CLUSTER_CAP})),
            priority_safety = {SAFETY_WEIGHT} * (CASE WHEN c.safety_flag THEN 1 ELSE 0 END)
        WHERE c.cluster_id IS NULL
        """
    )

    op.execute(
        """
        UPDATE complaint_clusters cl
        SET independent_student_count = GREATEST(1, sub.n)
        FROM (
            SELECT cluster_id, COUNT(DISTINCT COALESCE(student_id, id::text)) AS n
            FROM complaints
            WHERE cluster_id IS NOT NULL
            GROUP BY cluster_id
        ) sub
        WHERE cl.id = sub.cluster_id
        """
    )
    # Re-derive is_recurring from the (correct) independent-student count,
    # repairing clusters the old member_count rule over-flagged.
    op.execute(
        "UPDATE complaint_clusters SET is_recurring = (independent_student_count >= 3)"
    )


def downgrade() -> None:
    op.drop_column("complaint_clusters", "independent_student_count")
    op.alter_column(
        "complaints",
        "photo_url",
        existing_type=sa.Text(),
        type_=sa.String(2048),
        existing_nullable=True,
    )
    op.drop_constraint(
        "fk_complaints_suggested_match_complaint_id", "complaints", type_="foreignkey"
    )
    op.drop_column("complaints", "department_overridden")
    op.drop_column("complaints", "suggested_similarity")
    op.drop_column("complaints", "suggested_match_complaint_id")
    op.drop_column("complaints", "priority_sla_age")
    op.drop_column("complaints", "priority_safety")
    op.drop_column("complaints", "priority_frequency")
    op.drop_column("complaints", "priority_severity")
    op.drop_column("complaints", "photo_matches_text")
