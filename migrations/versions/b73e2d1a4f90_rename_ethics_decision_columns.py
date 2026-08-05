"""Rename legacy supervisor/ethics decision columns.

Revision ID: b73e2d1a4f90
Revises: d4e5f6a7b8c9
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "b73e2d1a4f90"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    for table_name in ("form_a", "form_b", "form_c"):
        columns = _columns(table_name)

        if "ethics_status" not in columns:
            if "ethics_form_status" in columns:
                op.alter_column(
                    table_name, "ethics_form_status", new_column_name="ethics_status"
                )
            else:
                op.add_column(table_name, sa.Column("ethics_status", sa.Text(), nullable=True))

        columns = _columns(table_name)
        if "ethics_signature_date" not in columns and "supervisor_signature_date" in columns:
            op.alter_column(
                table_name,
                "supervisor_signature_date",
                new_column_name="ethics_signature_date",
            )


def downgrade() -> None:
    for table_name in ("form_a", "form_b", "form_c"):
        columns = _columns(table_name)
        if "ethics_status" in columns and "ethics_form_status" not in columns:
            op.alter_column(table_name, "ethics_status", new_column_name="ethics_form_status")

        columns = _columns(table_name)
        if "ethics_signature_date" in columns and "supervisor_signature_date" not in columns:
            op.alter_column(
                table_name,
                "ethics_signature_date",
                new_column_name="supervisor_signature_date",
            )
