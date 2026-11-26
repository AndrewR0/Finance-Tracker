"""add category counts_as_saving

Revision ID: e119ac191543
Revises: 9718535ce5ef
Create Date: 2026-11-26 10:20:22.765907

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e119ac191543'
down_revision: Union[str, Sequence[str], None] = '9718535ce5ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A plain ADD COLUMN, not batch mode: batch mode copies the table and drops the old one,
    # and SQLite refuses to drop categories while transactions point at it (foreign keys).
    op.add_column('categories', sa.Column('counts_as_saving', sa.Boolean(), server_default=sa.text('0'), nullable=False))

    # Data migration: turn it on for the existing "Savings (Extra)" category and its
    # subcategories (Roth IRA, Investments). Does nothing on a database without one.
    op.execute(
        """
        UPDATE categories SET counts_as_saving = 1
        WHERE id IN (SELECT id FROM categories
                     WHERE name = 'Savings (Extra)' AND kind = 'expense' AND parent_id IS NULL)
           OR parent_id IN (SELECT id FROM categories
                            WHERE name = 'Savings (Extra)' AND kind = 'expense' AND parent_id IS NULL)
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    # SQLite 3.35+ can drop a column in place, so no table copy here either.
    op.drop_column('categories', 'counts_as_saving')
