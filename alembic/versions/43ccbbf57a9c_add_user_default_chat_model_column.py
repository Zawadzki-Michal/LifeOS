"""add user default_chat_model column

Revision ID: 43ccbbf57a9c
Revises: d1db6691153d
Create Date: 2026-07-24 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '43ccbbf57a9c'
down_revision: Union[str, Sequence[str], None] = 'd1db6691153d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user', sa.Column('default_chat_model', sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('user', 'default_chat_model')
