"""record who filed each complaint, and in what capacity

The report form used to ask for a bare `student_id` and treat it as
optional, which made two things impossible to answer from a row: who
actually reported this, and whether they were a student or a member of
staff. Both matter operationally — a teacher reporting a broken lab is a
different signal from one student reporting it, and a facilities team
following up needs a name rather than an opaque handle.

`student_id` stays exactly as it was and keeps its meaning: it is the
identity key that the recurring-issue rule counts distinctly, so touching
it would change what "three independent students" means. The new columns
sit beside it as description, not identity.

Both are nullable, and deliberately so. Every complaint already in the
database was filed before the form asked for a name, and a NOT NULL column
would mean either dropping that history or inventing names for it. The
form requires both; the schema records what it was given.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str]] = None
depends_on: Union[str, Sequence[str]] = None


def upgrade() -> None:
    op.add_column(
        "complaints", sa.Column("reporter_name", sa.String(255), nullable=True)
    )
    op.add_column(
        "complaints", sa.Column("reporter_role", sa.String(16), nullable=True)
    )
    # A closed set rather than free text: the dashboard filters and counts on
    # it, and "teacher"/"Teacher"/"faculty" arriving from three clients would
    # split one group into three.
    op.create_check_constraint(
        "ck_complaints_reporter_role",
        "complaints",
        "reporter_role IS NULL OR reporter_role IN ('student', 'teacher')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_complaints_reporter_role", "complaints", type_="check")
    op.drop_column("complaints", "reporter_role")
    op.drop_column("complaints", "reporter_name")
