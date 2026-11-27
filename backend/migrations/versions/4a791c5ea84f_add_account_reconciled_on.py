"""add account reconciled_on

Revision ID: 4a791c5ea84f
Revises: 3f0ca1bbbd48
Create Date: 2026-11-26 19:16:17.957029

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a791c5ea84f'
down_revision: Union[str, Sequence[str], None] = '3f0ca1bbbd48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A plain ADD COLUMN, not batch mode: batch mode copies the table and drops the old one,
    # and SQLite refuses to drop accounts while transactions point at it (foreign keys).
    op.add_column('accounts', sa.Column('reconciled_on', sa.Date(), nullable=True))
    # Data migration: start from each account's latest reconcile adjustment, if it has one.
    op.execute(
        """
        UPDATE accounts SET reconciled_on = (
            SELECT MAX(date) FROM transactions
            WHERE transactions.account_id = accounts.id
              AND transactions.is_adjustment = 1
              AND transactions.notes = 'Balance adjustment'
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('accounts', 'reconciled_on')
