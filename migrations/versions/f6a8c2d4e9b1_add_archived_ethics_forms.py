"""Add read-only archive storage for ethics forms.

Revision ID: f6a8c2d4e9b1
Revises: e18b4c72a5d9
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f6a8c2d4e9b1"
down_revision: Union[str, None] = "e18b4c72a5d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("archived_ethics_forms"):
        return
    op.create_table(
        "archived_ethics_forms",
        sa.Column("archive_id", sa.String(length=255), nullable=False),
        sa.Column("form_type", sa.String(length=20), nullable=False),
        sa.Column("original_form_id", sa.String(length=255), nullable=False),
        sa.Column("student_user_id", sa.String(length=255), nullable=False),
        sa.Column("student_name", sa.String(length=255), nullable=True),
        sa.Column("student_email", sa.String(length=255), nullable=True),
        sa.Column("original_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("original_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_by_user_id", sa.String(length=255), nullable=False),
        sa.Column("archive_reason", sa.Text(), nullable=True),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("archive_id"),
    )
    op.create_index(
        "ix_archived_ethics_forms_form_type",
        "archived_ethics_forms",
        ["form_type"],
        unique=False,
    )
    op.create_index(
        "ix_archived_ethics_forms_original_form_id",
        "archived_ethics_forms",
        ["original_form_id"],
        unique=False,
    )
    op.create_index(
        "ix_archived_ethics_forms_student_user_id",
        "archived_ethics_forms",
        ["student_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_archived_ethics_forms_archived_at",
        "archived_ethics_forms",
        ["archived_at"],
        unique=False,
    )


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("archived_ethics_forms"):
        return
    op.drop_index("ix_archived_ethics_forms_archived_at", table_name="archived_ethics_forms")
    op.drop_index("ix_archived_ethics_forms_student_user_id", table_name="archived_ethics_forms")
    op.drop_index("ix_archived_ethics_forms_original_form_id", table_name="archived_ethics_forms")
    op.drop_index("ix_archived_ethics_forms_form_type", table_name="archived_ethics_forms")
    op.drop_table("archived_ethics_forms")
