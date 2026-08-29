"""Add provenance, event sync status, odds probabilities, and constraints

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 1. collection_run_id provenance ---
    op.add_column('matches', sa.Column('collection_run_id', sa.Integer(), sa.ForeignKey('collection_runs.id'), nullable=True))
    op.add_column('match_events', sa.Column('collection_run_id', sa.Integer(), sa.ForeignKey('collection_runs.id'), nullable=True))
    op.add_column('odds_snapshots', sa.Column('collection_run_id', sa.Integer(), sa.ForeignKey('collection_runs.id'), nullable=True))
    op.add_column('ranking_snapshots', sa.Column('collection_run_id', sa.Integer(), sa.ForeignKey('collection_runs.id'), nullable=True))

    op.create_index('ix_matches_collection_run', 'matches', ['collection_run_id'])
    op.create_index('ix_events_collection_run', 'match_events', ['collection_run_id'])
    op.create_index('ix_odds_collection_run', 'odds_snapshots', ['collection_run_id'])
    op.create_index('ix_ranking_snaps_collection_run', 'ranking_snapshots', ['collection_run_id'])

    # --- 2. event_sync_status on matches ---
    op.add_column('matches', sa.Column('event_sync_status', sa.String(20), nullable=True))
    # NOT_APPLICABLE for upcoming, COMPLETE/INCOMPLETE for completed
    op.execute("""
        UPDATE matches SET event_sync_status = 'NOT_APPLICABLE' WHERE status = 'UPCOMING'
    """)

    # --- 3. Normalized odds probabilities ---
    op.add_column('odds_snapshots', sa.Column('raw_implied_home', sa.Numeric(10, 6), nullable=True))
    op.add_column('odds_snapshots', sa.Column('raw_implied_draw', sa.Numeric(10, 6), nullable=True))
    op.add_column('odds_snapshots', sa.Column('raw_implied_away', sa.Numeric(10, 6), nullable=True))
    op.add_column('odds_snapshots', sa.Column('overround', sa.Numeric(10, 6), nullable=True))
    op.add_column('odds_snapshots', sa.Column('normalized_home_prob', sa.Numeric(10, 6), nullable=True))
    op.add_column('odds_snapshots', sa.Column('normalized_draw_prob', sa.Numeric(10, 6), nullable=True))
    op.add_column('odds_snapshots', sa.Column('normalized_away_prob', sa.Numeric(10, 6), nullable=True))

    # Backfill existing odds snapshots
    op.execute("""
        UPDATE odds_snapshots
        SET raw_implied_home = 1.0 / home_odds,
            raw_implied_draw = 1.0 / draw_odds,
            raw_implied_away = 1.0 / away_odds,
            overround = (1.0/home_odds + 1.0/draw_odds + 1.0/away_odds) - 1.0,
            normalized_home_prob = (1.0/home_odds) / (1.0/home_odds + 1.0/draw_odds + 1.0/away_odds),
            normalized_draw_prob = (1.0/draw_odds) / (1.0/home_odds + 1.0/draw_odds + 1.0/away_odds),
            normalized_away_prob = (1.0/away_odds) / (1.0/home_odds + 1.0/draw_odds + 1.0/away_odds)
        WHERE home_odds > 0 AND draw_odds > 0 AND away_odds > 0
    """)

    # --- 4. Improved collection_run metrics ---
    op.add_column('collection_runs', sa.Column('matches_inserted', sa.Integer(), server_default='0'))
    op.add_column('collection_runs', sa.Column('matches_updated', sa.Integer(), server_default='0'))
    op.add_column('collection_runs', sa.Column('results_rows_seen', sa.Integer(), server_default='0'))
    op.add_column('collection_runs', sa.Column('results_persisted', sa.Integer(), server_default='0'))
    op.add_column('collection_runs', sa.Column('events_inserted', sa.Integer(), server_default='0'))
    op.add_column('collection_runs', sa.Column('events_duplicates_skipped', sa.Integer(), server_default='0'))
    op.add_column('collection_runs', sa.Column('odds_inserted', sa.Integer(), server_default='0'))
    op.add_column('collection_runs', sa.Column('odds_duplicates_skipped', sa.Integer(), server_default='0'))


def downgrade() -> None:
    op.drop_column('collection_runs', 'odds_duplicates_skipped')
    op.drop_column('collection_runs', 'odds_inserted')
    op.drop_column('collection_runs', 'events_duplicates_skipped')
    op.drop_column('collection_runs', 'events_inserted')
    op.drop_column('collection_runs', 'results_persisted')
    op.drop_column('collection_runs', 'results_rows_seen')
    op.drop_column('collection_runs', 'matches_updated')
    op.drop_column('collection_runs', 'matches_inserted')

    op.drop_column('odds_snapshots', 'normalized_away_prob')
    op.drop_column('odds_snapshots', 'normalized_draw_prob')
    op.drop_column('odds_snapshots', 'normalized_home_prob')
    op.drop_column('odds_snapshots', 'overround')
    op.drop_column('odds_snapshots', 'raw_implied_away')
    op.drop_column('odds_snapshots', 'raw_implied_draw')
    op.drop_column('odds_snapshots', 'raw_implied_home')

    op.drop_column('matches', 'event_sync_status')

    op.drop_index('ix_ranking_snaps_collection_run', 'ranking_snapshots')
    op.drop_index('ix_odds_collection_run', 'odds_snapshots')
    op.drop_index('ix_events_collection_run', 'match_events')
    op.drop_index('ix_matches_collection_run', 'matches')
    op.drop_column('ranking_snapshots', 'collection_run_id')
    op.drop_column('odds_snapshots', 'collection_run_id')
    op.drop_column('match_events', 'collection_run_id')
    op.drop_column('matches', 'collection_run_id')
