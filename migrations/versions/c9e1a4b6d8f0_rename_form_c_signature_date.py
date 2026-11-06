"""Rename Form C supervisor signature timestamp.

Revision ID: c9e1a4b6d8f0
Revises: b8d0f3a5c7e9
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c9e1a4b6d8f0"
down_revision: Union[str, None] = "b8d0f3a5c7e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("form_c"):
        return
    columns = {column["name"] for column in inspector.get_columns("form_c")}
    if "signature_date" in columns and "supervisor_signature_date" not in columns:
        op.alter_column("form_c", "signature_date", new_column_name="supervisor_signature_date")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("form_c"):
        return
    columns = {column["name"] for column in inspector.get_columns("form_c")}
    if "supervisor_signature_date" in columns and "signature_date" not in columns:
        op.alter_column("form_c", "supervisor_signature_date", new_column_name="signature_date")
