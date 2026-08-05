"""Repair ethics workflow columns required by the legacy ORM.

Revision ID: c84f2a91d6e0
Revises: b73e2d1a4f90
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "c84f2a91d6e0"
down_revision: Union[str, None] = "b73e2d1a4f90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table_name in ("form_a", "form_b", "form_c"):
        columns = {
            column["name"]
            for column in inspect(op.get_bind()).get_columns(table_name)
        }
        required_columns = {
            "form_supervisor_status": sa.Text(),
            "ethics_status": sa.Text(),
            "ethics_signature": sa.Text(),
            "ethics_signature_date": sa.DateTime(timezone=True),
        }
        for column_name, column_type in required_columns.items():
            if column_name not in columns:
                op.add_column(
                    table_name,
                    sa.Column(column_name, column_type, nullable=True),
                )


def downgrade() -> None:
    # These columns can contain live workflow decisions. A downgrade must not
    # discard them automatically.
    pass
