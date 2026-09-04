"""Add league_name to matches

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-08-30
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'e6f7a8b9c0d1'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('matches', sa.Column('league_name', sa.String(255), nullable=True))
    op.create_index('ix_matches_league_name', 'matches', ['league_name'])

    # Backfill from leagues table
    op.execute("""
        UPDATE matches m
        SET league_name = l.name
        FROM leagues l
        WHERE m.league_id = l.id AND m.league_name IS NULL
    """)


def downgrade() -> None:
    op.drop_index('ix_matches_league_name', 'matches')
    op.drop_column('matches', 'league_name')
