"""Merge the integrated and standalone ethics migration histories.

Revision ID: e18b4c72a5d9
Revises: d95a31f7c2b4, ab822f4227ac
"""

from typing import Sequence, Union


revision: str = "e18b4c72a5d9"
down_revision: Union[str, Sequence[str], None] = (
    "d95a31f7c2b4",
    "ab822f4227ac",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
