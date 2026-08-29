from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from typing import Optional, List, Dict, Tuple
from datetime import datetime
import logging

from app.models.database_models import Match, MatchEvent, Team
from app.normalization.team_normalizer import normalize_team_name

logger = logging.getLogger(__name__)


class ResultsRepository:
    def __init__(self, session: Session):
        self.session = session
        self._team_cache: Dict[int, str] = {}       # team_id → source_name
        self._match_cache: Optional[List[Match]] = None

    def _load_team_cache(self):
        """Load all team names into memory once."""
        if not self._team_cache:
            for team in self.session.execute(select(Team)).scalars().all():
                self._team_cache[team.id] = team.source_name

    def _load_match_cache(self, league_id: int):
        """Load all UPCOMING matches for the league once."""
        if self._match_cache is None:
            self._match_cache = self.session.execute(
                select(Match).filter(
                    Match.league_id == league_id,
                    Match.status == "UPCOMING"
                )
            ).scalars().all()

    def _get_match_name(self, match: Match) -> str:
        """Build 'Home vs Away' name string from match IDs."""
        home = self._team_cache.get(match.home_team_id, "")
        away = self._team_cache.get(match.away_team_id, "")
        return f"{home} vs {away}"

    def reconcile_and_save_result(
        self,
        external_id: Optional[int],
        league_id: int,
        home_team_name: str,
        away_team_name: str,
        scheduled_at: Optional[datetime],
        home_score: float,
        away_score: float,
        goals: List[dict],
        match_name: Optional[str] = None,
        round_number: Optional[int] = None,
        half_home_score: Optional[int] = None,
        half_away_score: Optional[int] = None,
        collection_run_id: Optional[int] = None
    ) -> Tuple[Optional[Match], bool]:
        """
        Phase 10: Match Reconciliation.
        Connects results back to the original Match created during the 'Matches' phase.
        Returns (match, was_newly_completed).
        """
        # Ensure caches are loaded
        self._load_team_cache()
        self._load_match_cache(league_id)

        match = None

        # Strategy 1: Match by name field (most reliable for results API)
        if match_name and self._match_cache:
            target = match_name.lower()
            for candidate in self._match_cache:
                candidate_name = self._get_match_name(candidate)
                if candidate_name.lower() == target:
                    match = candidate
                    break

        # Strategy 2: Match by normalized team names
        if not match and self._match_cache:
            norm_home = normalize_team_name(home_team_name)
            norm_away = normalize_team_name(away_team_name)
            for candidate in self._match_cache:
                home_name = normalize_team_name(self._team_cache.get(candidate.home_team_id, ""))
                away_name = normalize_team_name(self._team_cache.get(candidate.away_team_id, ""))
                if home_name == norm_home and away_name == norm_away:
                    match = candidate
                    break

        # Strategy 3: Match by external_id if non-zero (fallback)
        if not match and external_id and external_id != 0:
            match = self.session.execute(
                select(Match).filter_by(external_id=external_id)
            ).scalar_one_or_none()

        newly_completed = False
        if match and match.status != "COMPLETED":
            match.status = "COMPLETED"
            match.completed_at = datetime.utcnow()
            match.home_score = int(home_score)
            match.away_score = int(away_score)
            match.half_home_score = half_home_score
            match.half_away_score = half_away_score
            newly_completed = True

            if home_score > away_score:
                match.result = "HOME"
            elif away_score > home_score:
                match.result = "AWAY"
            else:
                match.result = "DRAW"

            if collection_run_id:
                match.collection_run_id = collection_run_id

            # Save goal events (with dedup: skip if event already exists
            # for this match at the same minute — e.g. from playout source)
            existing_events = self.session.execute(
                select(MatchEvent.minute).filter_by(match_id=match.id, event_type="GOAL")
            ).scalars().all()
            existing_minutes = set(existing_events)

            saved_goals = 0
            skipped_goals = 0
            for goal in goals:
                minute = goal.get('minute', 0)
                if minute in existing_minutes:
                    skipped_goals += 1
                    continue

                scoring_team = goal.get('team', '')
                team_id = None
                if scoring_team.lower() == 'home':
                    team_id = match.home_team_id
                elif scoring_team.lower() == 'away':
                    team_id = match.away_team_id

                event = MatchEvent(
                    match_id=match.id,
                    event_type="GOAL",
                    team_id=team_id,
                    team_name=scoring_team,
                    minute=minute,
                    captured_at=datetime.utcnow(),
                    collection_run_id=collection_run_id
                )
                self.session.add(event)
                existing_minutes.add(minute)
                saved_goals += 1

            if skipped_goals > 0:
                logger.info(f"  Dedup: skipped {skipped_goals} existing goal event(s) for match {match.id}")

            logger.info(f"Reconciled: {home_team_name} {int(home_score)}:{int(away_score)} {away_team_name} (match {match.id})")

        return match, newly_completed
