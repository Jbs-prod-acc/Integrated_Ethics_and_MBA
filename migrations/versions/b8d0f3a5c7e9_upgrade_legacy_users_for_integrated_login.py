"""Upgrade legacy users for integrated application login.

Revision ID: b8d0f3a5c7e9
Revises: a7c9e2f4b6d8
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b8d0f3a5c7e9"
down_revision: Union[str, None] = "a7c9e2f4b6d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("users"):
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    legacy_schema = "integrated_id" not in columns
    additions = {
        "integrated_id": sa.BigInteger(),
        "mba_role": sa.String(length=40),
        "scholar_role": sa.String(length=40),
        "ethics_role": sa.String(length=40),
        "has_profile": sa.Boolean(),
        "has_signature": sa.Boolean(),
        "has_cv": sa.Boolean(),
        "mba_access": sa.Boolean(),
        "ethics_access": sa.Boolean(),
        "authenticated_student": sa.Boolean(),
        "supervisor_integrated_id": sa.BigInteger(),
        "watched_demo": sa.Boolean(),
        "microsoft_subject": sa.String(length=255),
        "first_name": sa.String(length=120),
        "last_name": sa.String(length=120),
        "is_active": sa.Boolean(),
        "popia_confirmed_at": sa.DateTime(),
        "popia_notice_version": sa.String(length=40),
        "popia_confirmed_ip": sa.String(length=64),
        "popia_confirmed_user_agent": sa.String(length=255),
        "created_at": sa.DateTime(),
        "updated_at": sa.DateTime(),
    }
    for name, column_type in additions.items():
        if name not in columns:
            op.add_column("users", sa.Column(name, column_type, nullable=True))

    op.execute("CREATE SEQUENCE IF NOT EXISTS users_integrated_id_seq")
    op.execute("ALTER TABLE users ALTER COLUMN integrated_id SET DEFAULT nextval('users_integrated_id_seq')")
    op.execute("UPDATE users SET integrated_id = nextval('users_integrated_id_seq') WHERE integrated_id IS NULL")
    op.execute("ALTER TABLE users ALTER COLUMN integrated_id SET NOT NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_integrated_id ON users(integrated_id)")
    if legacy_schema:
        op.execute(
        """
        UPDATE users
        SET has_profile = COALESCE(has_profile, FALSE),
            has_signature = COALESCE(has_signature, FALSE),
            has_cv = COALESCE(has_cv, FALSE),
            authenticated_student = COALESCE(authenticated_student, FALSE),
            watched_demo = COALESCE(watched_demo, FALSE),
            is_active = COALESCE(is_active, TRUE),
            created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
            updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP),
            ethics_access = TRUE,
            mba_role = COALESCE(
                mba_role,
                CASE upper(role::text)
                    WHEN 'SUPER_ADMIN' THEN 'main_admin'
                    WHEN 'ADMIN' THEN 'admin'
                    WHEN 'SUPERVISOR' THEN 'scholar'
                    WHEN 'REVIEWER' THEN 'examiner'
                    WHEN 'REC' THEN 'hdc'
                    ELSE 'student'
                END
            ),
            scholar_role = COALESCE(
                scholar_role,
                CASE upper(role::text)
                    WHEN 'SUPERVISOR' THEN 'supervisor'
                    WHEN 'REVIEWER' THEN 'examiner'
                    ELSE NULL
                END
            ),
            ethics_role = COALESCE(ethics_role, lower(role::text)),
            mba_access = CASE
                WHEN upper(role::text) IN ('SUPER_ADMIN', 'ADMIN') THEN TRUE
                ELSE FALSE
            END
        """
        )
    for name in (
        "has_profile", "has_signature", "has_cv", "mba_access", "ethics_access",
        "authenticated_student", "watched_demo", "is_active", "created_at", "updated_at",
    ):
        op.alter_column("users", name, nullable=False)


def downgrade() -> None:
    # These columns contain integrated account and authorization data. A downgrade
    # deliberately preserves them rather than destructively reverting user records.
    pass
