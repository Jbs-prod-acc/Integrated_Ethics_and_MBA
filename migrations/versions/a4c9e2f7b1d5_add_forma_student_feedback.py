"""Add student responses to reviewer feedback for Forms A, B, and C.

Revision ID: a4c9e2f7b1d5
Revises: c9e1a4b6d8f0
"""

from alembic import op
import sqlalchemy as sa


revision = "a4c9e2f7b1d5"
down_revision = "c9e1a4b6d8f0"
branch_labels = None
depends_on = None


def upgrade():
    for table_name in ("form_a", "form_b", "form_c"):
        op.add_column(table_name, sa.Column("student_org_permission_comment", sa.Text(), nullable=True))
        op.add_column(table_name, sa.Column("student_waiver_comment", sa.Text(), nullable=True))
        op.add_column(table_name, sa.Column("student_form_comment", sa.Text(), nullable=True))
        op.add_column(table_name, sa.Column("student_questions_comment", sa.Text(), nullable=True))
        op.add_column(table_name, sa.Column("student_consent_comment", sa.Text(), nullable=True))
        op.add_column(table_name, sa.Column("student_proposal_comment", sa.Text(), nullable=True))
        op.add_column(table_name, sa.Column("student_general_comment", sa.Text(), nullable=True))
        op.add_column(
            table_name,
            sa.Column("student_feedback_submitted_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(table_name, sa.Column("student_feedback_source_form_id", sa.String(255), nullable=True))
        op.add_column(table_name, sa.Column("ethics_decision", sa.String(80), nullable=True))
        op.execute(
            sa.text(
                f'''UPDATE "{table_name}"
                    SET ethics_decision = COALESCE(
                        NULLIF(TRIM(form_review_comment1), ''),
                        NULLIF(TRIM(form_review_comment), ''),
                        NULLIF(TRIM(review_recommendation1), ''),
                        NULLIF(TRIM(review_recommendation), '')
                    )
                    WHERE ethics_decision IS NULL'''
            )
        )


def downgrade():
    for table_name in ("form_c", "form_b", "form_a"):
        op.drop_column(table_name, "ethics_decision")
        op.drop_column(table_name, "student_feedback_source_form_id")
        op.drop_column(table_name, "student_feedback_submitted_at")
        op.drop_column(table_name, "student_general_comment")
        op.drop_column(table_name, "student_proposal_comment")
        op.drop_column(table_name, "student_consent_comment")
        op.drop_column(table_name, "student_questions_comment")
        op.drop_column(table_name, "student_form_comment")
        op.drop_column(table_name, "student_waiver_comment")
        op.drop_column(table_name, "student_org_permission_comment")
