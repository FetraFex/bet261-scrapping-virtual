import asyncio
import argparse
import sys
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker

from app.monitoring.logger import setup_logging
from app.services.collection_service import CollectionService
from app.config.settings import settings
from app.models.database_models import (
    Match, OddsSnapshot, MatchEvent, RankingSnapshot, RankingEntry,
    Team, League, CollectionRun, RawPayload
)

logger = logging.getLogger(__name__)

async def run_collect_once():
    service = CollectionService()
    try:
        await service.collect_once()
    finally:
        await service.close()

async def run_forever():
    service = CollectionService()
    try:
        await service.run_forever()
    except KeyboardInterrupt:
        logger.info("Collector stopped by user.")
    finally:
        await service.close()

def run_status():
    """Query the database and show actual collection stats."""
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    with SessionLocal() as session:
        # Basic counts
        total_matches = session.query(func.count(Match.id)).scalar() or 0
        upcoming = session.query(func.count(Match.id)).filter(Match.status == "UPCOMING").scalar() or 0
        completed = session.query(func.count(Match.id)).filter(Match.status == "COMPLETED").scalar() or 0
        total_odds = session.query(func.count(OddsSnapshot.id)).scalar() or 0
        total_goals = session.query(func.count(MatchEvent.id)).scalar() or 0
        total_rankings = session.query(func.count(RankingSnapshot.id)).scalar() or 0
        total_teams = session.query(func.count(Team.id)).scalar() or 0
        total_raw = session.query(func.count(RawPayload.id)).scalar() or 0
        total_runs = session.query(func.count(CollectionRun.id)).scalar() or 0
        
        # Last collection run
        last_run = session.query(CollectionRun).order_by(CollectionRun.started_at.desc()).first()
        
        print("=" * 60)
        print("  Virtual League Collector — Status")
        print("=" * 60)
        print(f"  League ID:        {settings.LEAGUE_ID}")
        print(f"  Total Matches:    {total_matches} ({upcoming} upcoming, {completed} completed)")
        print(f"  Odds Snapshots:   {total_odds}")
        print(f"  Goals Events:     {total_goals}")
        print(f"  Ranking Snapshots:{total_rankings}")
        print(f"  Teams Tracked:    {total_teams}")
        print(f"  Raw Payloads:     {total_raw}")
        print(f"  Collection Runs:  {total_runs}")
        print()
        
        if last_run:
            print(f"  Last Run:         {last_run.started_at}")
            print(f"  Status:           {last_run.status}")
            print(f"  Matches Collected:{last_run.matches_collected}")
            print(f"  Results Collected:{last_run.results_collected}")
            print(f"  Goals Collected:  {last_run.goals_collected}")
            if last_run.error_message:
                print(f"  Error:            {last_run.error_message[:100]}")
        else:
            print("  No collection runs recorded yet.")
        
        print("=" * 60)

def run_export(export_dir: str = None):
    """Export database tables to CSV and Parquet files."""
    if not export_dir:
        export_dir = str(settings.RAW_DATA_DIR.parent / "exports")
    
    export_path = Path(export_dir)
    export_path.mkdir(parents=True, exist_ok=True)
    
    engine = create_engine(settings.DATABASE_URL)
    
    print(f"Exporting to {export_path}...")
    
    # Export matches
    matches_df = pd.read_sql_table("matches", engine)
    matches_df.to_csv(export_path / "matches.csv", index=False)
    print(f"  Exported {len(matches_df)} matches to matches.csv")
    
    # Export odds snapshots
    odds_df = pd.read_sql_table("odds_snapshots", engine)
    odds_df.to_csv(export_path / "odds_snapshots.csv", index=False)
    print(f"  Exported {len(odds_df)} odds snapshots to odds_snapshots.csv")
    
    # Export match events
    events_df = pd.read_sql_table("match_events", engine)
    events_df.to_csv(export_path / "match_events.csv", index=False)
    print(f"  Exported {len(events_df)} match events to match_events.csv")
    
    # Export ranking snapshots
    rankings_df = pd.read_sql_table("ranking_snapshots", engine)
    rankings_df.to_csv(export_path / "ranking_snapshots.csv", index=False)
    print(f"  Exported {len(rankings_df)} ranking snapshots to ranking_snapshots.csv")
    
    # Export ranking entries
    entries_df = pd.read_sql_table("ranking_entries", engine)
    entries_df.to_csv(export_path / "ranking_entries.csv", index=False)
    print(f"  Exported {len(entries_df)} ranking entries to ranking_entries.csv")
    
    # Export collection runs
    runs_df = pd.read_sql_table("collection_runs", engine)
    runs_df.to_csv(export_path / "collection_runs.csv", index=False)
    print(f"  Exported {len(runs_df)} collection runs to collection_runs.csv")
    
    # Generate integrated ML dataset
    _generate_ml_dataset(engine, export_path)
    
    print("Export completed!")

def _generate_ml_dataset(engine, export_path: Path):
    """Generate an integrated ML dataset with pre-match features only."""
    matches_df = pd.read_sql_table("matches", engine)
    odds_df = pd.read_sql_table("odds_snapshots", engine)
    teams_df = pd.read_sql_table("teams", engine)
    rankings_df = pd.read_sql_table("ranking_entries", engine)
    
    if matches_df.empty:
        print("  No matches to generate ML dataset from.")
        return
    
    # Merge odds (opening and closing) with matches
    if not odds_df.empty:
        odds_cols = ["match_id", "captured_at", "home_odds", "draw_odds", "away_odds",
                     "normalized_home_prob", "normalized_draw_prob", "normalized_away_prob"]
        odds_df_slim = odds_df[odds_cols].copy()
        
        # Get opening odds (first snapshot per match)
        opening = odds_df_slim.sort_values("captured_at").groupby("match_id").first().reset_index()
        opening.columns = ["match_id", "opening_captured_at",
                           "opening_home_odds", "opening_draw_odds", "opening_away_odds",
                           "opening_normalized_home_prob", "opening_normalized_draw_prob", "opening_normalized_away_prob"]
        
        # Get closing odds (last snapshot per match)
        closing = odds_df_slim.sort_values("captured_at").groupby("match_id").last().reset_index()
        closing.columns = ["match_id", "closing_captured_at",
                           "closing_home_odds", "closing_draw_odds", "closing_away_odds",
                           "closing_normalized_home_prob", "closing_normalized_draw_prob", "closing_normalized_away_prob"]
        
        ml_df = matches_df.merge(opening[["match_id", "opening_home_odds", "opening_draw_odds", "opening_away_odds",
                                           "opening_normalized_home_prob", "opening_normalized_draw_prob", "opening_normalized_away_prob"]],
                                left_on="id", right_on="match_id", how="left")
        ml_df = ml_df.merge(closing[["match_id", "closing_home_odds", "closing_draw_odds", "closing_away_odds",
                                      "closing_normalized_home_prob", "closing_normalized_draw_prob", "closing_normalized_away_prob"]],
                           left_on="id", right_on="match_id", how="left", suffixes=("", "_closing"))
    else:
        ml_df = matches_df.copy()
    
    # Use pre-computed normalized probabilities from odds_snapshots (already sum to 1.0)
    if "opening_normalized_home_prob" in ml_df.columns:
        ml_df["implied_home_prob"] = ml_df["opening_normalized_home_prob"]
        ml_df["implied_draw_prob"] = ml_df["opening_normalized_draw_prob"]
        ml_df["implied_away_prob"] = ml_df["opening_normalized_away_prob"]
    elif "opening_home_odds" in ml_df.columns:
        # Fallback: compute from raw odds if normalized columns missing (legacy data)
        raw_h = 1.0 / ml_df["opening_home_odds"].replace(0, 1)
        raw_d = 1.0 / ml_df["opening_draw_odds"].replace(0, 1)
        raw_a = 1.0 / ml_df["opening_away_odds"].replace(0, 1)
        total = raw_h + raw_d + raw_a
        ml_df["implied_home_prob"] = raw_h / total
        ml_df["implied_draw_prob"] = raw_d / total
        ml_df["implied_away_prob"] = raw_a / total
    
    # Add team names from teams table
    if not teams_df.empty:
        team_map = dict(zip(teams_df["id"], teams_df["canonical_name"]))
        ml_df["home_team_name"] = ml_df["home_team_id"].map(team_map)
        ml_df["away_team_name"] = ml_df["away_team_id"].map(team_map)
    
    # Save ML dataset
    ml_df.to_csv(export_path / "ml_dataset.csv", index=False)
    print(f"  Generated ML dataset with {len(ml_df)} matches")

def run_validate():
    """Validate the collected data for completeness and consistency."""
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    issues = []
    
    with SessionLocal() as session:
        # Check for matches without odds
        matches_without_odds = session.execute(text("""
            SELECT COUNT(*) FROM matches m 
            LEFT JOIN odds_snapshots o ON m.id = o.match_id 
            WHERE o.id IS NULL
        """)).scalar()
        if matches_without_odds > 0:
            issues.append(f"WARNING: {matches_without_odds} matches have no odds snapshots")
        
        # Check for matches with status UPCOMING that have scores
        mismatched = session.execute(text("""
            SELECT COUNT(*) FROM matches 
            WHERE status = 'UPCOMING' AND (home_score IS NOT NULL OR away_score IS NOT NULL)
        """)).scalar()
        if mismatched > 0:
            issues.append(f"WARNING: {mismatched} matches have status UPCOMING but have scores")
        
        # Check for matches with status COMPLETED but no scores
        incomplete = session.execute(text("""
            SELECT COUNT(*) FROM matches 
            WHERE status = 'COMPLETED' AND (home_score IS NULL OR away_score IS NULL)
        """)).scalar()
        if incomplete > 0:
            issues.append(f"WARNING: {incomplete} matches have status COMPLETED but no scores")
        
        # Check for duplicate external_ids
        dupes = session.execute(text("""
            SELECT external_id, COUNT(*) as cnt 
            FROM matches 
            WHERE external_id IS NOT NULL AND external_id != 0
            GROUP BY external_id 
            HAVING COUNT(*) > 1
        """)).fetchall()
        if dupes:
            issues.append(f"WARNING: {len(dupes)} duplicate external_ids found")
        
        # Check for temporal leakage (future features in ML dataset)
        # This validates that odds snapshots were captured BEFORE match completion
        leakage = session.execute(text("""
            SELECT COUNT(*) FROM matches m 
            JOIN odds_snapshots o ON m.id = o.match_id 
            WHERE m.completed_at IS NOT NULL 
            AND o.captured_at > m.completed_at
        """)).scalar()
        if leakage > 0:
            issues.append(f"WARNING: {leakage} odds snapshots were captured after match completion (possible data leakage)")
        
        # Check for collection runs with errors
        error_runs = session.query(func.count(CollectionRun.id)).filter(
            CollectionRun.status == "FAILED"
        ).scalar() or 0
        if error_runs > 0:
            issues.append(f"INFO: {error_runs} failed collection runs recorded")
        
        # Summary
        total_matches = session.query(func.count(Match.id)).scalar() or 0
        total_odds = session.query(func.count(OddsSnapshot.id)).scalar() or 0
        total_events = session.query(func.count(MatchEvent.id)).scalar() or 0
        
        print("=" * 60)
        print("  Virtual League Collector — Data Validation")
        print("=" * 60)
        print(f"  Total Matches:    {total_matches}")
        print(f"  Total Odds:       {total_odds}")
        print(f"  Total Events:     {total_events}")
        print()
        
        if issues:
            for issue in issues:
                print(f"  {issue}")
        else:
            print("  [OK] All validation checks passed!")
        
        print("=" * 60)

def run_backfill(rounds: int = 5):
    """Backfill historical data for previous rounds."""
    async def _backfill():
        service = CollectionService()
        try:
            logger.info(f"Starting backfill for {rounds} rounds...")
            # Collect with larger result window
            with service.SessionLocal() as session:
                results_data = await service.results_scraper.collect(
                    skip=0, take=rounds * 24, db_session=session
                )
                session.commit()
            logger.info(f"Backfill completed for up to {rounds * 24} results")
        finally:
            await service.close()
    
    asyncio.run(_backfill())

def main():
    setup_logging()
    
    parser = argparse.ArgumentParser(description="Virtual League Collector")
    parser.add_argument("command", 
                       choices=["collect-once", "run", "status", "export", "validate", "backfill"], 
                       help="Command to run")
    parser.add_argument("--rounds", type=int, default=5, help="Number of rounds to backfill")
    parser.add_argument("--output", type=str, default=None, help="Output directory for exports")
    
    args = parser.parse_args()
    
    if args.command == "collect-once":
        asyncio.run(run_collect_once())
    elif args.command == "run":
        asyncio.run(run_forever())
    elif args.command == "status":
        run_status()
    elif args.command == "export":
        run_export(args.output)
    elif args.command == "validate":
        run_validate()
    elif args.command == "backfill":
        run_backfill(args.rounds)
        
if __name__ == "__main__":
    main()
