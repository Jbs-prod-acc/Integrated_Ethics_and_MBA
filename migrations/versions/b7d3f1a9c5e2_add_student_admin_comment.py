"""Add a separate student response field for Ethics Admin feedback.

Revision ID: b7d3f1a9c5e2
Revises: a4c9e2f7b1d5
"""

from alembic import op


revision = "b7d3f1a9c5e2"
down_revision = "a4c9e2f7b1d5"
branch_labels = None
depends_on = None


def upgrade():
    for table_name in ("form_a", "form_b", "form_c"):
        op.execute(
            f'ALTER TABLE "{table_name}" '
            'ADD COLUMN IF NOT EXISTS student_admin_comment TEXT'
        )
        op.execute(
            f'ALTER TABLE "{table_name}" '
            'ADD COLUMN IF NOT EXISTS student_admin_comment_submitted_at TIMESTAMP WITH TIME ZONE'
        )


def downgrade():
    for table_name in ("form_c", "form_b", "form_a"):
        op.drop_column(table_name, "student_admin_comment_submitted_at")
        op.drop_column(table_name, "student_admin_comment")
