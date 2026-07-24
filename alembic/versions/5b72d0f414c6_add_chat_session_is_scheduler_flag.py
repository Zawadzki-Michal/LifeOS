"""add chat_session is_scheduler flag

Revision ID: 5b72d0f414c6
Revises: dfac71ceb261
Create Date: 2026-07-24 06:30:09.712232

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b72d0f414c6'
down_revision: Union[str, Sequence[str], None] = 'dfac71ceb261'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'chat_session',
        sa.Column('is_scheduler', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chat_session', 'is_scheduler')
