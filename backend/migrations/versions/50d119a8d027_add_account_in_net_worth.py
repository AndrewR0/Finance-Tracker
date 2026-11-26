"""add account in_net_worth

Revision ID: 50d119a8d027
Revises: e119ac191543
Create Date: 2026-11-26 11:11:15.150128

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50d119a8d027'
down_revision: Union[str, Sequence[str], None] = 'e119ac191543'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A plain ADD COLUMN, not batch mode: batch mode copies the table and drops the old one,
    # and SQLite refuses to drop accounts while transactions point at it (foreign keys).
    # Every existing account keeps counting in net worth.
    op.add_column('accounts', sa.Column('in_net_worth', sa.Boolean(), server_default=sa.text('1'), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('accounts', 'in_net_worth')
