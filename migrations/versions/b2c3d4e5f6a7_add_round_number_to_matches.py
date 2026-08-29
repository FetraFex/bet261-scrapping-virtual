"""Add round_number to matches

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-25 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('matches', sa.Column('round_number', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_matches_round_number'), 'matches', ['round_number'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_matches_round_number'), table_name='matches')
    op.drop_column('matches', 'round_number')
