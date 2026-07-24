"""add openrouter_usage_log table

Revision ID: b7e1a2f9c4d3
Revises: 43ccbbf57a9c
Create Date: 2026-07-24 17:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e1a2f9c4d3'
down_revision: Union[str, Sequence[str], None] = '43ccbbf57a9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'openrouter_usage_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('cost', sa.Numeric(12, 6), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('openrouter_usage_log')
