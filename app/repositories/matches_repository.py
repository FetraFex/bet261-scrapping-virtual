from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional, Tuple
from datetime import datetime
import logging

from app.models.database_models import Match, Team, League, OddsSnapshot
from app.normalization.team_normalizer import normalize_team_name
from app.utils.hashing import calculate_hash

logger = logging.getLogger(__name__)

class MatchRepository:
    def __init__(self, session: Session):
        self.session = session
        
    def get_or_create_league(self, external_id: int, name: str) -> League:
        league = self.session.execute(
            select(League).filter_by(external_id=external_id)
        ).scalar_one_or_none()
        
        if not league:
            league = League(external_id=external_id, name=name, category="VIRTUAL")
            self.session.add(league)
            self.session.flush()
        return league
        
    def get_or_create_team(self, league_id: int, source_name: str) -> Team:
        canonical = normalize_team_name(source_name)
        team = self.session.execute(
            select(Team).filter_by(league_id=league_id, source_name=source_name)
        ).scalar_one_or_none()
        
        if not team:
            team = Team(league_id=league_id, source_name=source_name, canonical_name=canonical)
            self.session.add(team)
            self.session.flush()
        return team
        
    def save_match(
        self, 
        league_id: int,
        home_team_id: int,
        away_team_id: int,
        external_id: int,
        scheduled_at: Optional[datetime],
        home_odds: float,
        draw_odds: float,
        away_odds: float,
        odds_raw_hash: str
    ) -> Match:
        """
        Deduplicates matches and manages odds history.
        """
        # Match Identification (Phase 9)
        # Try to find by external_id first
        match = self.session.execute(
            select(Match).filter_by(external_id=external_id)
        ).scalar_one_or_none()
        
        # If not found by external ID, fallback to league + scheduled + teams
        if not match and scheduled_at:
            match = self.session.execute(
                select(Match).filter_by(
                    league_id=league_id,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    scheduled_at=scheduled_at
                )
            ).scalar_one_or_none()
            
        if not match:
            match = Match(
                external_id=external_id,
                league_id=league_id,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                scheduled_at=scheduled_at,
                status="UPCOMING"
            )
            self.session.add(match)
            self.session.flush()
            logger.info(f"Created new match: ID {match.id}")
        else:
            match.last_seen_at = datetime.utcnow()
            
        # Handle Odds History (Phase 4)
        latest_odds = self.session.execute(
            select(OddsSnapshot)
            .filter_by(match_id=match.id)
            .order_by(OddsSnapshot.captured_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        # Only create a new snapshot if odds changed
        if not latest_odds or (
            latest_odds.home_odds != home_odds or 
            latest_odds.draw_odds != draw_odds or 
            latest_odds.away_odds != away_odds
        ):
            new_odds = OddsSnapshot(
                match_id=match.id,
                home_odds=home_odds,
                draw_odds=draw_odds,
                away_odds=away_odds,
                raw_hash=odds_raw_hash
            )
            self.session.add(new_odds)
            logger.info(f"Recorded new odds for match {match.id}: {home_odds} | {draw_odds} | {away_odds}")
            
        return match
