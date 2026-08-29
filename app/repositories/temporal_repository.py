"""
Temporal join query helpers.

Every feature used for prediction MUST be retrieved through these helpers,
which enforce the strict constraint: information_timestamp < prediction_time.

This prevents data leakage from future information.
"""
from datetime import datetime
from typing import List, Optional, Tuple, Dict
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func
import logging

from app.models.database_models import (
    Match, OddsSnapshot, MatchEvent, RankingSnapshot, RankingEntry, Team
)

logger = logging.getLogger(__name__)


class TemporalRepository:
    """
    Query repository that enforces temporal constraints for ML features.
    
    All queries use: information_timestamp < cutoff_time
    This ensures no future data leaks into predictions.
    """

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Odds queries
    # ------------------------------------------------------------------

    def get_odds_before(
        self,
        match_id: int,
        cutoff_time: datetime,
        limit: Optional[int] = None,
    ) -> List[OddsSnapshot]:
        """
        Get all odds snapshots for a match captured BEFORE cutoff_time.
        
        Args:
            match_id: The match to query odds for.
            cutoff_time: Only snapshots with captured_at < this time.
            limit: Maximum snapshots to return (None = all).
        
        Returns:
            Chronologically sorted list of OddsSnapshot objects.
        """
        stmt = (
            select(OddsSnapshot)
            .filter(
                OddsSnapshot.match_id == match_id,
                OddsSnapshot.captured_at < cutoff_time,
            )
            .order_by(OddsSnapshot.captured_at.asc())
        )
        if limit:
            stmt = stmt.limit(limit)
        
        return list(self.session.execute(stmt).scalars().all())

    def get_latest_odds_before(
        self,
        match_id: int,
        cutoff_time: datetime,
    ) -> Optional[OddsSnapshot]:
        """
        Get the most recent odds snapshot for a match captured BEFORE cutoff_time.
        
        Returns:
            The latest OddsSnapshot, or None if no odds exist before cutoff.
        """
        stmt = (
            select(OddsSnapshot)
            .filter(
                OddsSnapshot.match_id == match_id,
                OddsSnapshot.captured_at < cutoff_time,
            )
            .order_by(OddsSnapshot.captured_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_opening_odds_before(
        self,
        match_id: int,
        cutoff_time: datetime,
    ) -> Optional[OddsSnapshot]:
        """
        Get the earliest odds snapshot for a match captured BEFORE cutoff_time.
        This represents the 'opening odds' available before prediction.
        """
        stmt = (
            select(OddsSnapshot)
            .filter(
                OddsSnapshot.match_id == match_id,
                OddsSnapshot.captured_at < cutoff_time,
            )
            .order_by(OddsSnapshot.captured_at.asc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_odds_movement_before(
        self,
        match_id: int,
        cutoff_time: datetime,
    ) -> Dict[str, float]:
        """
        Compute odds movement features using only snapshots before cutoff_time.
        
        Returns dict with:
            opening_home_odds, opening_draw_odds, opening_away_odds
            latest_home_odds, latest_draw_odds, latest_away_odds
            odds_home_movement, odds_draw_movement, odds_away_movement
            market_open_implied_home/draw/away
            market_latest_implied_home/draw/away
            market_open_overround, market_latest_overround
            n_snapshots
        """
        snapshots = self.get_odds_before(match_id, cutoff_time)
        
        if not snapshots:
            return {}
        
        first = snapshots[0]
        last = snapshots[-1]
        
        # Raw probabilities
        # Cast to float to handle SQLAlchemy Numeric/Decimal types
        open_h = float(first.home_odds)
        open_d = float(first.draw_odds)
        open_a = float(first.away_odds)
        lat_h = float(last.home_odds)
        lat_d = float(last.draw_odds)
        lat_a = float(last.away_odds)

        raw_open_home = 1.0 / open_h if open_h > 0 else 0
        raw_open_draw = 1.0 / open_d if open_d > 0 else 0
        raw_open_away = 1.0 / open_a if open_a > 0 else 0
        overround_open = raw_open_home + raw_open_draw + raw_open_away
        
        raw_lat_home = 1.0 / lat_h if lat_h > 0 else 0
        raw_lat_draw = 1.0 / lat_d if lat_d > 0 else 0
        raw_lat_away = 1.0 / lat_a if lat_a > 0 else 0
        overround_lat = raw_lat_home + raw_lat_draw + raw_lat_away
        
        features = {
            "opening_home_odds": open_h,
            "opening_draw_odds": open_d,
            "opening_away_odds": open_a,
            "latest_home_odds": lat_h,
            "latest_draw_odds": lat_d,
            "latest_away_odds": lat_a,
            "odds_home_movement": lat_h - open_h,
            "odds_draw_movement": lat_d - open_d,
            "odds_away_movement": lat_a - open_a,
            "market_open_implied_home": raw_open_home / overround_open if overround_open > 0 else 0,
            "market_open_implied_draw": raw_open_draw / overround_open if overround_open > 0 else 0,
            "market_open_implied_away": raw_open_away / overround_open if overround_open > 0 else 0,
            "market_latest_implied_home": raw_lat_home / overround_lat if overround_lat > 0 else 0,
            "market_latest_implied_draw": raw_lat_draw / overround_lat if overround_lat > 0 else 0,
            "market_latest_implied_away": raw_lat_away / overround_lat if overround_lat > 0 else 0,
            "market_open_overround": overround_open,
            "market_latest_overround": overround_lat,
            "n_snapshots": len(snapshots),
        }
        
        return features

    # ------------------------------------------------------------------
    # Ranking queries
    # ------------------------------------------------------------------

    def get_latest_ranking_before(
        self,
        league_id: int,
        cutoff_time: datetime,
    ) -> Optional[Tuple[RankingSnapshot, List[RankingEntry]]]:
        """
        Get the most recent ranking snapshot and its entries for a league
        captured BEFORE cutoff_time.
        
        Returns:
            Tuple of (snapshot, entries) or (None, []) if no ranking exists.
        """
        snapshot = self.session.execute(
            select(RankingSnapshot)
            .filter(
                RankingSnapshot.league_id == league_id,
                RankingSnapshot.captured_at < cutoff_time,
            )
            .order_by(RankingSnapshot.captured_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        if not snapshot:
            return None, []
        
        entries = list(self.session.execute(
            select(RankingEntry)
            .filter(RankingEntry.snapshot_id == snapshot.id)
            .order_by(RankingEntry.rank.asc())
        ).scalars().all())
        
        return snapshot, entries

    def get_team_ranking_before(
        self,
        league_id: int,
        team_id: int,
        cutoff_time: datetime,
    ) -> Optional[Dict]:
        """
        Get a team's ranking stats from the most recent snapshot before cutoff_time.
        
        Returns:
            Dict with rank, points, form, or None if not found.
        """
        result = self.get_latest_ranking_before(league_id, cutoff_time)
        if not result[0]:
            return None
        
        _, entries = result
        for entry in entries:
            if entry.team_id == team_id:
                return {
                    "rank": entry.rank,
                    "points": entry.points,
                    "form": [
                        entry.form_position_1,
                        entry.form_position_2,
                        entry.form_position_3,
                        entry.form_position_4,
                        entry.form_position_5,
                    ],
                }
        return None

    # ------------------------------------------------------------------
    # Events queries
    # ------------------------------------------------------------------

    def get_events_before(
        self,
        match_id: int,
        cutoff_time: datetime,
    ) -> List[MatchEvent]:
        """
        Get all match events captured BEFORE cutoff_time.
        
        Note: For completed matches, events from the match itself are
        typically available only AFTER kickoff. For pre-match features,
        event history from *previous* matches should be used instead
        (see get_team_event_stats_before).
        """
        stmt = (
            select(MatchEvent)
            .filter(
                MatchEvent.match_id == match_id,
                MatchEvent.captured_at < cutoff_time,
            )
            .order_by(MatchEvent.minute.asc())
        )
        return list(self.session.execute(stmt).scalars().all())

    # ------------------------------------------------------------------
    # Match queries (for building historical features)
    # ------------------------------------------------------------------

    def get_completed_matches_before(
        self,
        league_id: int,
        cutoff_time: datetime,
        team_id: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Match]:
        """
        Get completed matches before cutoff_time, optionally filtered by team.
        Used for building historical form and goal stats.
        """
        stmt = (
            select(Match)
            .filter(
                Match.league_id == league_id,
                Match.status == "COMPLETED",
                Match.completed_at < cutoff_time,
            )
            .order_by(Match.completed_at.desc())
        )
        
        if team_id:
            stmt = stmt.filter(
                (Match.home_team_id == team_id) | (Match.away_team_id == team_id)
            )
        
        if limit:
            stmt = stmt.limit(limit)
        
        return list(self.session.execute(stmt).scalars().all())

    def get_team_form_before(
        self,
        league_id: int,
        team_id: int,
        cutoff_time: datetime,
        n_matches: int = 5,
    ) -> Dict[str, float]:
        """
        Compute team form statistics from completed matches before cutoff_time.
        
        Returns:
            Dict with form_points, wins, draws, losses, goals_for, goals_against,
            clean_sheets, n_matches_in_form.
        """
        matches = self.get_completed_matches_before(
            league_id, cutoff_time, team_id=team_id, limit=n_matches
        )
        
        if not matches:
            return {
                "form_points": 0,
                "form_wins": 0,
                "form_draws": 0,
                "form_losses": 0,
                "form_goals_for": 0,
                "form_goals_against": 0,
                "form_clean_sheets": 0,
                "form_matches": 0,
            }
        
        form_points = 0
        wins = draws = losses = 0
        goals_for = goals_against = clean_sheets = 0
        
        for match in matches:
            is_home = match.home_team_id == team_id
            gf = match.home_score if is_home else match.away_score
            ga = match.away_score if is_home else match.home_score
            
            # Default to 0 if None (shouldn't happen for completed matches)
            gf = gf or 0
            ga = ga or 0
            
            goals_for += gf
            goals_against += ga
            
            if ga == 0:
                clean_sheets += 1
            
            if gf > ga:
                form_points += 3
                wins += 1
            elif gf == ga:
                form_points += 1
                draws += 1
            else:
                losses += 1
        
        return {
            "form_points": form_points,
            "form_wins": wins,
            "form_draws": draws,
            "form_losses": losses,
            "form_goals_for": goals_for,
            "form_goals_against": goals_against,
            "form_clean_sheets": clean_sheets,
            "form_matches": len(matches),
        }

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def check_temporal_integrity(
        self,
        match_id: int,
        prediction_time: datetime,
    ) -> Dict[str, any]:
        """
        Check temporal integrity for a match: verify no features use
        information from after the prediction time.
        
        Returns:
            Dict with is_valid, violations list, and details.
        """
        violations = []
        
        # Check odds: all odds snapshots should be before prediction_time
        future_odds = self.session.execute(
            select(func.count(OddsSnapshot.id)).filter(
                OddsSnapshot.match_id == match_id,
                OddsSnapshot.captured_at > prediction_time,
            )
        ).scalar()
        
        if future_odds > 0:
            violations.append(
                f"Match {match_id}: {future_odds} odds snapshots captured at/after prediction time"
            )
        
        # Check events: for pre-match features, no events should exist before kickoff
        # For post-match analysis, events are fine after completion
        # This is informational only — events are typically captured after the match
        
        # Check match completion: if match was completed before prediction_time,
        # the result was already known — this is fine for historical analysis
        match = self.session.execute(
            select(Match).filter(Match.id == match_id)
        ).scalar_one_or_none()
        
        if match and match.completed_at and match.completed_at < prediction_time:
            violations.append(
                f"Match {match_id}: completed_at ({match.completed_at}) is before prediction_time — "
                f"result was already known"
            )
        
        return {
            "match_id": match_id,
            "prediction_time": prediction_time,
            "is_valid": len(violations) == 0,
            "violations": violations,
        }
