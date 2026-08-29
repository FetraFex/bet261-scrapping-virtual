import asyncio
import logging
import signal
import time
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from app.config.settings import settings
from app.scrapers.matches_scraper import MatchesScraper
from app.scrapers.results_scraper import ResultsScraper
from app.scrapers.ranking_scraper import RankingScraper
from app.scrapers.playout_scraper import PlayoutScraper
from app.repositories.matches_repository import MatchRepository
from app.repositories.results_repository import ResultsRepository
from app.repositories.ranking_repository import RankingRepository
from app.utils.hashing import calculate_hash
from app.models.database_models import CollectionRun, ScraperError, Match, MatchEvent
import json

logger = logging.getLogger(__name__)

class CollectionService:
    def __init__(self):
        self.engine = create_engine(settings.DATABASE_URL)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        self.matches_scraper = MatchesScraper(settings.RAW_DATA_DIR)
        self.results_scraper = ResultsScraper(settings.RAW_DATA_DIR)
        self.ranking_scraper = RankingScraper(settings.RAW_DATA_DIR)
        self.playout_scraper = PlayoutScraper(settings.RAW_DATA_DIR)
        
        self._shutdown_requested = False
        
    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers for SIGINT/SIGTERM."""
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._handle_shutdown)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass
    
    def _handle_shutdown(self):
        """Handle graceful shutdown signal."""
        logger.info("Shutdown signal received, finishing current cycle...")
        self._shutdown_requested = True

    async def collect_once(self):
        logger.info(f"Starting collection run at {datetime.utcnow()}")
        run = CollectionRun(started_at=datetime.utcnow(), status="RUNNING")
        
        with self.SessionLocal() as session:
            try:
                # Track collection run
                session.add(run)
                session.flush()
                
                matches_repo = MatchRepository(session)
                results_repo = ResultsRepository(session)
                ranking_repo = RankingRepository(session)
                
                # Setup League
                league = matches_repo.get_or_create_league(settings.LEAGUE_ID, settings.LEAGUE_NAME)
                
                # 1. Collect Matches
                matches_data = await self.matches_scraper.collect(db_session=session)
                match_inserted = 0
                match_updated = 0
                odds_inserted = 0
                odds_skipped = 0
                for round_data in matches_data.rounds:
                    for m in round_data.matches:
                        home_team = matches_repo.get_or_create_team(league.id, m.homeTeam.name)
                        away_team = matches_repo.get_or_create_team(league.id, m.awayTeam.name)
                        
                        # Find 1x2 odds from eventBetTypeItems
                        home_odds = 0.0
                        draw_odds = 0.0
                        away_odds = 0.0
                        for bt in m.eventBetTypes:
                            if bt.name.upper() == "1X2":
                                for item in bt.eventBetTypeItems:
                                    if item.shortName == "1": home_odds = item.odds
                                    elif item.shortName.upper() == "X": draw_odds = item.odds
                                    elif item.shortName == "2": away_odds = item.odds
                        
                        # Determine scheduled_at
                        scheduled_at = m.expectedStart
                        if scheduled_at is not None:
                            if scheduled_at.year <= 1:
                                scheduled_at = round_data.expectedStart
                        if scheduled_at is None:
                            scheduled_at = round_data.expectedStart
                        
                        match, was_new, odds_new = matches_repo.save_match(
                            league_id=league.id,
                            home_team_id=home_team.id,
                            away_team_id=away_team.id,
                            external_id=m.id,
                            scheduled_at=scheduled_at,
                            home_odds=home_odds,
                            draw_odds=draw_odds,
                            away_odds=away_odds,
                            odds_raw_hash=calculate_hash(f"{m.id}_{home_odds}_{draw_odds}_{away_odds}"),
                            round_number=round_data.roundNumber,
                            collection_run_id=run.id
                        )
                        if was_new:
                            match_inserted += 1
                        else:
                            match_updated += 1
                        if odds_new:
                            odds_inserted += 1
                        else:
                            odds_skipped += 1
                
                run.matches_collected = match_inserted + match_updated
                run.matches_inserted = match_inserted
                run.matches_updated = match_updated
                run.odds_inserted = odds_inserted
                run.odds_duplicates_skipped = odds_skipped
                
                # 2. Collect Results
                results_data = await self.results_scraper.collect(skip=0, take=24, db_session=session)
                results_rows_seen = 0
                results_persisted = 0
                events_inserted = 0
                events_skipped = 0
                newly_completed_matches = []
                
                for round_data in results_data.get('rounds', []):
                    round_number = round_data.get('roundNumber', 0)
                    for result in round_data.get('matches', []):
                        results_rows_seen += 1
                        home_team_name = result.get('homeTeam', {}).get('name')
                        away_team_name = result.get('awayTeam', {}).get('name')
                        
                        if not home_team_name or not away_team_name:
                            continue
                        
                        # Parse score string
                        score_str = result.get('score', '0:0')
                        score_parts = score_str.split(':')
                        home_score = int(score_parts[0]) if len(score_parts) > 0 else 0
                        away_score = int(score_parts[1]) if len(score_parts) > 1 else 0
                        
                        # Parse half-time score string
                        ht_score_str = result.get('halfTimeScore', '0:0')
                        ht_parts = ht_score_str.split(':')
                        half_home_score = int(ht_parts[0]) if len(ht_parts) > 0 else 0
                        half_away_score = int(ht_parts[1]) if len(ht_parts) > 1 else 0
                        
                        # Parse expectedStart from result
                        scheduled_at = None
                        if result.get('expectedStart') and result['expectedStart'] != '0001-01-01T00:00:00Z':
                            try:
                                scheduled_at = datetime.fromisoformat(result['expectedStart'].replace('Z', '+00:00'))
                            except (ValueError, TypeError):
                                pass
                        
                        # Goals array with team info
                        goals = result.get('goals', [])
                        goal_events = []
                        for g in goals:
                            goal_events.append({
                                'minute': g.get('minute', 0),
                                'homeScore': g.get('homeScore', 0),
                                'awayScore': g.get('awayScore', 0),
                                'team': g.get('team', '')
                            })
                        
                        match_name = result.get('name', f"{home_team_name} vs {away_team_name}")
                        
                        match, was_newly_completed = results_repo.reconcile_and_save_result(
                            external_id=0,
                            league_id=league.id,
                            home_team_name=home_team_name,
                            away_team_name=away_team_name,
                            match_name=match_name,
                            round_number=round_number,
                            scheduled_at=scheduled_at,
                            home_score=home_score,
                            away_score=away_score,
                            half_home_score=half_home_score,
                            half_away_score=half_away_score,
                            goals=goal_events,
                            collection_run_id=run.id
                        )
                        
                        if match:
                            results_persisted += 1
                            # Count events from this reconciliation
                            events_inserted += len(goal_events)
                            if was_newly_completed:
                                newly_completed_matches.append({
                                    'match': match,
                                    'official_home': int(home_score),
                                    'official_away': int(away_score),
                                    'event_count': len(goal_events)
                                })
                
                run.results_rows_seen = results_rows_seen
                run.results_collected = results_rows_seen  # backward compat
                run.results_persisted = results_persisted
                run.events_inserted = events_inserted
                
                # 3. Collect Playout data + Final Event Sync
                for round_data in matches_data.rounds:
                    if round_data.matches:
                        playout_round = round_data.roundNumber
                        try:
                            playout_data = await self.playout_scraper.collect(
                                round_number=playout_round,
                                event_category_id=settings.LEAGUE_ID
                            )
                            for match_data in playout_data.get('matches', []):
                                match_ext_id = match_data.get('id')
                                if match_ext_id:
                                    match = session.execute(
                                        select(Match).filter_by(external_id=match_ext_id)
                                    ).scalar_one_or_none()
                                    if not match:
                                        continue
                                    goals = match_data.get('goals', [])
                                    # Dedup: load existing goal minutes for this match
                                    existing_minutes = set(session.execute(
                                        select(MatchEvent.minute).filter_by(
                                            match_id=match.id, event_type="GOAL"
                                        )
                                    ).scalars().all())
                                    prev_home = 0
                                    prev_away = 0
                                    skipped = 0
                                    for goal in goals:
                                        cur_home = int(goal.get('homeScore', 0))
                                        cur_away = int(goal.get('awayScore', 0))
                                        minute = goal.get('minute', 0)
                                        if minute in existing_minutes:
                                            skipped += 1
                                            prev_home = cur_home
                                            prev_away = cur_away
                                            continue
                                        team_id = None
                                        team_name = None
                                        if cur_home > prev_home:
                                            team_id = match.home_team_id
                                            team_name = "Home"
                                        elif cur_away > prev_away:
                                            team_id = match.away_team_id
                                            team_name = "Away"
                                        event = MatchEvent(
                                            match_id=match.id,
                                            event_type="GOAL",
                                            team_id=team_id,
                                            team_name=team_name,
                                            minute=minute,
                                            captured_at=datetime.utcnow(),
                                            collection_run_id=run.id
                                        )
                                        session.add(event)
                                        existing_minutes.add(minute)
                                        prev_home = cur_home
                                        prev_away = cur_away
                                    if skipped > 0:
                                        events_skipped += skipped
                                        logger.info(f"  Dedup: skipped {skipped} existing playout goal(s) for match {match.id}")
                        except Exception as e:
                            logger.warning(f"Could not fetch playout for round {playout_round}: {e}")
                            error = ScraperError(
                                collection_run_id=run.id,
                                source_type="playout",
                                error_type="fetch_error",
                                error_message=str(e),
                                endpoint=f"/instantleagues/round/{playout_round}/playout"
                            )
                            session.add(error)
                
                run.events_duplicates_skipped = events_skipped
                
                # 4. Final Event Sync for newly completed matches (bounded retry)
                await self._final_event_sync(session, newly_completed_matches, run)
                
                # 5. Collect Ranking
                ranking_data = await self.ranking_scraper.collect(db_session=session)
                raw_hash = calculate_hash(json.dumps(ranking_data))
                
                entries = []
                for idx, team_data in enumerate(ranking_data.get('teams', [])):
                    entries.append({
                        "team_name": team_data.get('name'),
                        "rank": team_data.get('position', idx + 1),
                        "points": team_data.get('points', 0),
                        "form": team_data.get('history', [])
                    })
                    
                ranking_repo.save_ranking(league.id, entries, raw_hash, collection_run_id=run.id)
                ranking_repo.link_ranking_team_ids(league.id)
                run.ranking_snapshots = 1
                
                # Commit all changes for this cycle
                run.status = "COMPLETED"
                run.completed_at = datetime.utcnow()
                session.commit()
                logger.info(
                    f"Collection run completed. "
                    f"Matches: +{match_inserted} new / {match_updated} seen, "
                    f"Results: {results_rows_seen} seen / {results_persisted} persisted, "
                    f"Events: {events_inserted} inserted / {events_skipped} skipped"
                )
                
            except Exception as e:
                session.rollback()
                run.status = "FAILED"
                run.error_message = str(e)
                run.completed_at = datetime.utcnow()
                session.commit()
                logger.error(f"Collection run failed: {e}", exc_info=True)
                raise

    async def _final_event_sync(self, session, newly_completed_matches, run):
        """After results are saved, re-fetch playout for newly completed matches
        to catch any events that appeared after the initial fetch.
        Uses bounded retry with configurable delay."""
        if not newly_completed_matches:
            return
        
        max_attempts = settings.EVENT_FINAL_SYNC_MAX_ATTEMPTS
        delay_ms = settings.EVENT_FINAL_SYNC_DELAY_MS
        
        for match_info in newly_completed_matches:
            match = match_info['match']
            official_home = match_info['official_home']
            official_away = match_info['official_away']
            official_total = official_home + official_away
            
            if official_total == 0:
                # 0-0 match — nothing to sync
                match.event_sync_status = "COMPLETE"
                continue
            
            # Count current events
            event_count = session.execute(
                select(MatchEvent).filter_by(match_id=match.id, event_type="GOAL")
            ).scalars().all()
            
            if len(event_count) >= official_total:
                match.event_sync_status = "COMPLETE"
                continue
            
            # If round_number is None, the playout API won't work — mark as UNKNOWN
            if not match.round_number:
                if len(event_count) > 0:
                    match.event_sync_status = "INCOMPLETE"
                else:
                    match.event_sync_status = "UNKNOWN"
                logger.info(
                    f"  Match {match.id}: round_number is None, cannot sync events. "
                    f"official={official_home}:{official_away} events={len(event_count)}"
                )
                continue
            
            # Events are missing — attempt bounded retry
            synced = False
            for attempt in range(1, max_attempts + 1):
                logger.info(f"  Final sync attempt {attempt}/{max_attempts} for match {match.id} "
                           f"(have {len(event_count)} events, need {official_total})")
                
                await asyncio.sleep(delay_ms / 1000.0)
                
                try:
                    playout_data = await self.playout_scraper.collect(
                        round_number=match.round_number,
                        event_category_id=settings.LEAGUE_ID
                    )
                    
                    for match_data in playout_data.get('matches', []):
                        if match_data.get('id') == match.external_id:
                            goals = match_data.get('goals', [])
                            existing_minutes = set(session.execute(
                                select(MatchEvent.minute).filter_by(
                                    match_id=match.id, event_type="GOAL"
                                )
                            ).scalars().all())
                            
                            prev_home = 0
                            prev_away = 0
                            for goal in goals:
                                cur_home = int(goal.get('homeScore', 0))
                                cur_away = int(goal.get('awayScore', 0))
                                minute = goal.get('minute', 0)
                                if minute in existing_minutes:
                                    prev_home = cur_home
                                    prev_away = cur_away
                                    continue
                                team_id = None
                                team_name = None
                                if cur_home > prev_home:
                                    team_id = match.home_team_id
                                    team_name = "Home"
                                elif cur_away > prev_away:
                                    team_id = match.away_team_id
                                    team_name = "Away"
                                event = MatchEvent(
                                    match_id=match.id,
                                    event_type="GOAL",
                                    team_id=team_id,
                                    team_name=team_name,
                                    minute=minute,
                                    captured_at=datetime.utcnow(),
                                    collection_run_id=run.id
                                )
                                session.add(event)
                                existing_minutes.add(minute)
                                prev_home = cur_home
                                prev_away = cur_away
                            break
                    
                    # Re-count
                    event_count = session.execute(
                        select(MatchEvent).filter_by(match_id=match.id, event_type="GOAL")
                    ).scalars().all()
                    
                    if len(event_count) >= official_total:
                        match.event_sync_status = "COMPLETE"
                        synced = True
                        logger.info(f"  Final sync: match {match.id} now complete ({len(event_count)} events)")
                        break
                        
                except Exception as e:
                    logger.warning(f"  Final sync attempt {attempt} failed for match {match.id}: {e}")
            
            if not synced:
                if len(event_count) > 0:
                    match.event_sync_status = "INCOMPLETE"
                    logger.warning(
                        f"  Match {match.id}: official={official_home}:{official_away} "
                        f"events={len(event_count)} after {max_attempts} attempts — marked INCOMPLETE"
                    )
                else:
                    match.event_sync_status = "UNKNOWN"
                    logger.warning(f"  Match {match.id}: no events found after {max_attempts} attempts — marked UNKNOWN")
                    
    async def run_forever(self):
        logger.info(f"Starting continuous collection (Interval: {settings.POLL_INTERVAL_SECONDS}s)")
        self._setup_signal_handlers()
        
        while not self._shutdown_requested:
            try:
                await self.collect_once()
            except Exception as e:
                logger.error(f"Error in continuous run: {e}")
                
            if self._shutdown_requested:
                break
                
            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)
        
        logger.info("Collector stopped gracefully.")
            
    async def close(self):
        await self.matches_scraper.close()
        await self.results_scraper.close()
        await self.ranking_scraper.close()
        await self.playout_scraper.close()
