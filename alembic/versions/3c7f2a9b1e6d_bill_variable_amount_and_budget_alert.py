"""bill.amount_is_fixed and expense_category.last_budget_alert

Revision ID: 3c7f2a9b1e6d
Revises: 9a1c2e4f7b3d
Create Date: 2026-07-22 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c7f2a9b1e6d'
down_revision: Union[str, Sequence[str], None] = '9a1c2e4f7b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'bill',
        sa.Column('amount_is_fixed', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column('expense_category', sa.Column('last_budget_alert', sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('expense_category', 'last_budget_alert')
    op.drop_column('bill', 'amount_is_fixed')
