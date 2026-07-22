"""add bill.category_id

Revision ID: 9a1c2e4f7b3d
Revises: fed897078ba5
Create Date: 2026-07-22 06:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a1c2e4f7b3d'
down_revision: Union[str, Sequence[str], None] = 'fed897078ba5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('bill', sa.Column('category_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'bill_category_id_fkey', 'bill', 'expense_category', ['category_id'], ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('bill_category_id_fkey', 'bill', type_='foreignkey')
    op.drop_column('bill', 'category_id')
