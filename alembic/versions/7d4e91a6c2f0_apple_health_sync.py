"""apple health sync: metric_daily kcal/avg_hr, apple_workout table

Revision ID: 7d4e91a6c2f0
Revises: 3c7f2a9b1e6d
Create Date: 2026-07-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d4e91a6c2f0'
down_revision: Union[str, Sequence[str], None] = '3c7f2a9b1e6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('metric_daily', sa.Column('active_kcal', sa.Numeric(7, 2), nullable=True))
    op.add_column('metric_daily', sa.Column('resting_kcal', sa.Numeric(7, 2), nullable=True))
    op.add_column('metric_daily', sa.Column('avg_hr', sa.Integer(), nullable=True))

    op.create_table(
        'apple_workout',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.String(length=200), nullable=False),
        sa.Column('workout_type', sa.String(length=64), nullable=False),
        sa.Column('start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('duration_min', sa.Numeric(6, 2), nullable=True),
        sa.Column('active_kcal', sa.Numeric(7, 2), nullable=True),
        sa.Column('distance_km', sa.Numeric(6, 2), nullable=True),
        sa.Column('avg_hr', sa.Integer(), nullable=True),
        sa.Column('max_hr', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('apple_workout')
    op.drop_column('metric_daily', 'avg_hr')
    op.drop_column('metric_daily', 'resting_kcal')
    op.drop_column('metric_daily', 'active_kcal')
