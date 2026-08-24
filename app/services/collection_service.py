import asyncio
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from app.config.settings import settings
from app.scrapers.matches_scraper import MatchesScraper
from app.scrapers.results_scraper import ResultsScraper
from app.scrapers.ranking_scraper import RankingScraper
from app.repositories.matches_repository import MatchRepository
from app.repositories.results_repository import ResultsRepository
from app.repositories.ranking_repository import RankingRepository
from app.utils.hashing import calculate_hash
import json

logger = logging.getLogger(__name__)

class CollectionService:
    def __init__(self):
        self.engine = create_engine(settings.DATABASE_URL)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        self.matches_scraper = MatchesScraper(settings.RAW_DATA_DIR)
        self.results_scraper = ResultsScraper(settings.RAW_DATA_DIR)
        self.ranking_scraper = RankingScraper(settings.RAW_DATA_DIR)
        
    async def collect_once(self):
        logger.info(f"Starting collection run at {datetime.utcnow()}")
        
        with self.SessionLocal() as session:
            try:
                matches_repo = MatchRepository(session)
                results_repo = ResultsRepository(session)
                ranking_repo = RankingRepository(session)
                
                # Setup League
                league = matches_repo.get_or_create_league(settings.LEAGUE_ID, settings.LEAGUE_NAME)
                
                # 1. Collect Matches
                matches_data = await self.matches_scraper.collect()
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
                                    
                        matches_repo.save_match(
                            league_id=league.id,
                            home_team_id=home_team.id,
                            away_team_id=away_team.id,
                            external_id=m.id,
                            scheduled_at=m.expectedStart,
                            home_odds=home_odds,
                            draw_odds=draw_odds,
                            away_odds=away_odds,
                            odds_raw_hash=calculate_hash(f"{m.id}_{home_odds}_{draw_odds}_{away_odds}")
                        )
                
                # 2. Collect Results
                results_data = await self.results_scraper.collect()
                for result in results_data.get('results', []):
                    home_team_name = result.get('homeTeam', {}).get('name')
                    away_team_name = result.get('awayTeam', {}).get('name')
                    
                    if not home_team_name or not away_team_name:
                        continue
                        
                    results_repo.reconcile_and_save_result(
                        external_id=result.get('id'),
                        league_id=league.id,
                        home_team_name=home_team_name,
                        away_team_name=away_team_name,
                        scheduled_at=None, # Extract from payload if available
                        home_score=result.get('homeScore', 0),
                        away_score=result.get('awayScore', 0),
                        goals=result.get('goals', [])
                    )
                
                # 3. Collect Ranking
                ranking_data = await self.ranking_scraper.collect()
                raw_hash = calculate_hash(json.dumps(ranking_data))
                
                entries = []
                for idx, team_data in enumerate(ranking_data.get('teams', [])):
                    entries.append({
                        "team_name": team_data.get('name'),
                        "rank": idx + 1,
                        "points": team_data.get('points', 0)
                    })
                    
                ranking_repo.save_ranking(league.id, entries, raw_hash)
                
                # Commit all changes for this cycle
                session.commit()
                logger.info("Collection run completed successfully.")
                
            except Exception as e:
                session.rollback()
                logger.error(f"Collection run failed: {e}", exc_info=True)
                raise
                
    async def run_forever(self):
        logger.info(f"Starting continuous collection (Interval: {settings.POLL_INTERVAL_SECONDS}s)")
        while True:
            try:
                await self.collect_once()
            except Exception as e:
                logger.error(f"Error in continuous run: {e}")
                
            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)
            
    async def close(self):
        await self.matches_scraper.close()
        await self.results_scraper.close()
        await self.ranking_scraper.close()
