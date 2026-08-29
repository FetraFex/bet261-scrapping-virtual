"""Add composite indexes for temporal queries and ML features

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Matches: composite indexes for temporal queries
    op.create_index('ix_matches_league_status', 'matches', ['league_id', 'status'])
    op.create_index('ix_matches_completed_at', 'matches', ['completed_at'])
    op.create_index('ix_matches_home_away_scheduled', 'matches', ['home_team_id', 'away_team_id', 'scheduled_at'])

    # Odds snapshots: composite index for temporal join (match_id, captured_at)
    op.create_index('ix_odds_match_captured', 'odds_snapshots', ['match_id', 'captured_at'])

    # Match events: composite index for querying by match + minute
    op.create_index('ix_events_match_minute', 'match_events', ['match_id', 'minute'])

    # Ranking entries: composite index for snapshot + team lookup
    op.create_index('ix_ranking_entries_snapshot_team', 'ranking_entries', ['snapshot_id', 'team_id'])


def downgrade() -> None:
    op.drop_index('ix_ranking_entries_snapshot_team', table_name='ranking_entries')
    op.drop_index('ix_events_match_minute', table_name='match_events')
    op.drop_index('ix_odds_match_captured', table_name='odds_snapshots')
    op.drop_index('ix_matches_home_away_scheduled', table_name='matches')
    op.drop_index('ix_matches_completed_at', table_name='matches')
    op.drop_index('ix_matches_league_status', table_name='matches')
