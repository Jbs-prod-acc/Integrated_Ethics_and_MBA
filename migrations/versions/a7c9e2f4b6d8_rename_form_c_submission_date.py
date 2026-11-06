"""Rename Form C submission timestamp to submitted_at.

Revision ID: a7c9e2f4b6d8
Revises: f6a8c2d4e9b1
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7c9e2f4b6d8"
down_revision: Union[str, None] = "f6a8c2d4e9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("form_c"):
        return
    columns = {column["name"] for column in inspector.get_columns("form_c")}
    if "submission_date" in columns and "submitted_at" not in columns:
        op.alter_column("form_c", "submission_date", new_column_name="submitted_at")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("form_c"):
        return
    columns = {column["name"] for column in inspector.get_columns("form_c")}
    if "submitted_at" in columns and "submission_date" not in columns:
        op.alter_column("form_c", "submitted_at", new_column_name="submission_date")
