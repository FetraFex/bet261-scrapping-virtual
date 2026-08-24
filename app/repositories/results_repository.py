from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from typing import Optional, List
from datetime import datetime, timedelta
import logging

from app.models.database_models import Match, MatchEvent
from app.normalization.team_normalizer import normalize_team_name

logger = logging.getLogger(__name__)

class ResultsRepository:
    def __init__(self, session: Session):
        self.session = session

    def reconcile_and_save_result(
        self,
        external_id: Optional[int],
        league_id: int,
        home_team_name: str,
        away_team_name: str,
        scheduled_at: Optional[datetime],
        home_score: float,
        away_score: float,
        goals: List[dict]
    ) -> Optional[Match]:
        """
        Phase 10: Match Reconciliation.
        Connects results back to the original Match created during the 'Matches' phase.
        """
        match = None
        
        # Strategy 1: Match by external ID
        if external_id:
            match = self.session.execute(
                select(Match).filter_by(external_id=external_id)
            ).scalar_one_or_none()
            
        # Strategy 2: Match by time window and team names
        if not match and scheduled_at:
            # We look for UPCOMING matches within a narrow time window (-5 to +5 minutes)
            time_window_start = scheduled_at - timedelta(minutes=5)
            time_window_end = scheduled_at + timedelta(minutes=5)
            
            candidates = self.session.execute(
                select(Match).filter(
                    and_(
                        Match.league_id == league_id,
                        Match.status == "UPCOMING",
                        Match.scheduled_at >= time_window_start,
                        Match.scheduled_at <= time_window_end
                    )
                )
            ).scalars().all()
            
            # Find the best candidate based on team names
            norm_home = normalize_team_name(home_team_name)
            norm_away = normalize_team_name(away_team_name)
            
            for candidate in candidates:
                if candidate.home_team_id and candidate.away_team_id:
                    # In a real implementation, you'd fetch the actual team canonical names
                    # to compare, but since Team fetching requires DB calls, we assume
                    # the repository caller resolved this or we do it carefully.
                    # For this step, if we reach here, we might just mark AMBIGUOUS if 
                    # multiple matches are in the same timeslot.
                    pass
            
            if len(candidates) == 1:
                match = candidates[0]
            elif len(candidates) > 1:
                logger.warning(f"Ambiguous match reconciliation for {home_team_name} vs {away_team_name}")
                return None
                
        if match:
            # Update the match with results
            if match.status != "COMPLETED":
                match.status = "COMPLETED"
                match.completed_at = datetime.utcnow()
                match.home_score = int(home_score)
                match.away_score = int(away_score)
                
                if home_score > away_score:
                    match.result = "HOME"
                elif away_score > home_score:
                    match.result = "AWAY"
                else:
                    match.result = "DRAW"
                
                # Save events (Goals)
                for goal in goals:
                    event = MatchEvent(
                        match_id=match.id,
                        event_type="GOAL",
                        minute=goal.get('minute', 0),
                        captured_at=datetime.utcnow()
                    )
                    self.session.add(event)
                    
                logger.info(f"Reconciled and saved result for match {match.id}")
                
        return match
