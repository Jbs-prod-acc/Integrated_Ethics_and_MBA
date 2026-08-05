"""Synchronize legitimate database changes from the standalone ethics app.

Revision ID: d95a31f7c2b4
Revises: c84f2a91d6e0

The standalone repository contains two divergent Alembic histories. This
revision consolidates their additive changes without importing the generated
revision whose upgrade drops all ethics tables.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d95a31f7c2b4"
down_revision: Union[str, None] = "c84f2a91d6e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _add_missing_columns(table_name: str, columns: dict[str, sa.types.TypeEngine]) -> None:
    if table_name not in _table_names():
        return
    existing = _column_names(table_name)
    for name, column_type in columns.items():
        if name not in existing:
            op.add_column(table_name, sa.Column(name, column_type, nullable=True))


def upgrade() -> None:
    _add_missing_columns(
        "users",
        {
            "staff_number": sa.String(255),
            "specialisation": sa.String(255),
            "authenticate_student": sa.String(),
        },
    )

    requirement_binary_fields = (
        "needs_permission_pending",
        "pending_note",
        "permission_letter",
        "prior_clearance_path",
        "prior_clearance",
        "need_jbs_clearance1",
        "need_jbs_clearance",
        "prior_clearance1",
        "research_tools_path",
        "proposal_path",
        "impact_assessment_path",
        "participation_info_sheet",
        "ethics_evidence_path",
        "files",
    )
    requirement_columns: dict[str, sa.types.TypeEngine] = {
        name: sa.LargeBinary() for name in requirement_binary_fields
    }
    requirement_columns.update(
        {
            f"{name}_filename": sa.Text()
            for name in requirement_binary_fields
            if name not in {
                "research_tools_path",
                "impact_assessment_path",
                "participation_info_sheet",
                "ethics_evidence_path",
            }
        }
    )
    requirement_columns.update(
        {
            "research_tools_filename": sa.Text(),
            "impact_assessment_filename": sa.Text(),
            "participation_info_filename": sa.Text(),
            "ethics_evidence_path_filename": sa.Text(),
            "form_type": sa.String(),
            "needs_permission": sa.Boolean(),
            "has_clearance": sa.Boolean(),
            "company_requires_jbs": sa.Boolean(),
            "has_ethics_evidence": sa.Boolean(),
            "ethics_evidence": sa.Boolean(),
            "submitted_at": sa.DateTime(timezone=True),
            "updated_at": sa.DateTime(timezone=True),
        }
    )
    _add_missing_columns("form_a_requirements", requirement_columns)

    for table_name in ("form_a", "form_b", "form_c"):
        _add_missing_columns(
            table_name,
            {"created_at": sa.DateTime(timezone=True)},
        )

    _add_missing_columns(
        "form_b",
        {
            "permission_letter_filename": sa.String(255),
            "prior_clearance_filename": sa.String(255),
            "ethics_evidence_filename": sa.String(255),
            "proposal_path": sa.LargeBinary(),
            "proposal_filename": sa.String(255),
            "pending_note": sa.LargeBinary(),
            "pending_note_filename": sa.String(255),
            "private_permission_file": sa.LargeBinary(),
            "private_permission_filename": sa.String(255),
            "personal_info_comment": sa.Text(),
        },
    )

    tables = _table_names()
    if "login_logs" not in tables:
        op.create_table(
            "login_logs",
            sa.Column("log_id", sa.String(255), primary_key=True),
            sa.Column("user_id", sa.String(255), nullable=False),
            sa.Column(
                "login_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        )
        op.create_index("ix_login_logs_user_id", "login_logs", ["user_id"])
        op.create_index("ix_login_logs_login_at", "login_logs", ["login_at"])
    else:
        _add_missing_columns(
            "login_logs",
            {
                "ip_address": sa.String(64),
                "user_agent": sa.Text(),
            },
        )

    if "user_activity_logs" not in tables:
        op.create_table(
            "user_activity_logs",
            sa.Column("activity_id", sa.String(255), primary_key=True),
            sa.Column("user_id", sa.String(255), nullable=False),
            sa.Column("action", sa.String(100), nullable=False),
            sa.Column("page", sa.String(255), nullable=True),
            sa.Column("target_user_id", sa.String(255), nullable=True),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("user_agent", sa.String(255), nullable=True),
            sa.Column("details", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
            sa.ForeignKeyConstraint(["target_user_id"], ["users.user_id"]),
        )
        op.create_index(
            "ix_user_activity_logs_user_id", "user_activity_logs", ["user_id"]
        )
        op.create_index(
            "ix_user_activity_logs_timestamp", "user_activity_logs", ["timestamp"]
        )
    else:
        _add_missing_columns(
            "user_activity_logs",
            {
                "user_agent": sa.String(255),
                "details": sa.Text(),
            },
        )


def downgrade() -> None:
    # This synchronization may repair columns already used by production data.
    # Never drop them automatically.
    pass
