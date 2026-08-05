"""Historical marker for the production database revision.

Revision ID: 12d0695114c7
Revises:

The original migration with this identifier lives in the legacy ``alembic``
tree.  Flask-Migrate uses ``migrations`` and therefore needs this no-op marker
to recognize databases that were stamped by the legacy tree.  The production
schema already contains the original revision's changes.
"""


revision = "12d0695114c7"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
