"""
Feature store for ML predictions.

Wires feature building to the database via temporal join queries.
Every feature is retrieved using the strict constraint:
    information_timestamp < prediction_time

This prevents data leakage from future information.
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
import logging

from app.models.database_models import Match, Team
from app.repositories.temporal_repository import TemporalRepository
from app.ml.baselines import build_match_features, odds_movement_features, odds_to_market_probabilities

logger = logging.getLogger(__name__)


class FeatureStore:
    """
    Builds feature vectors for matches using only temporally-valid data.
    
    Usage:
        store = FeatureStore(session)
        features = store.build_prediction_features(
            match_id=123,
            prediction_time=datetime(2026, 8, 29, 10, 0, 0),
            league_id=1,
        )
    """

    def __init__(self, session: Session):
        self.session = session
        self.temporal = TemporalRepository(session)

    def build_prediction_features(
        self,
        match_id: int,
        prediction_time: datetime,
        league_id: int,
        include_form: bool = True,
        form_window: int = 5,
    ) -> Dict[str, float]:
        """
        Build a complete feature vector for predicting a match outcome.
        
        All data is strictly filtered to: timestamp < prediction_time.
        
        Args:
            match_id: The match to build features for.
            prediction_time: The timestamp at which the prediction is made.
            league_id: The league this match belongs to.
            include_form: Whether to include historical form features.
            form_window: Number of recent matches for form calculation.
        
        Returns:
            Dict of feature_name -> feature_value.
        """
        match = self.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")
        
        features = {}
        
        # --- Identity features ---
        features["home_team_id"] = float(match.home_team_id)
        features["away_team_id"] = float(match.away_team_id)
        features["round_number"] = float(match.round_number or 0)
        
        # --- Odds features (temporal) ---
        odds_features = self.temporal.get_odds_movement_before(match_id, prediction_time)
        if odds_features:
            features.update(odds_features)
        else:
            # No odds available — fill with zeros
            for key in [
                "opening_home_odds", "opening_draw_odds", "opening_away_odds",
                "latest_home_odds", "latest_draw_odds", "latest_away_odds",
                "odds_home_movement", "odds_draw_movement", "odds_away_movement",
                "market_open_implied_home", "market_open_implied_draw", "market_open_implied_away",
                "market_latest_implied_home", "market_latest_implied_draw", "market_latest_implied_away",
                "market_open_overround", "market_latest_overround",
                "n_snapshots",
            ]:
                features[key] = 0.0
        
        # --- Ranking features (temporal) ---
        home_ranking = self.temporal.get_team_ranking_before(
            league_id, match.home_team_id, prediction_time
        )
        away_ranking = self.temporal.get_team_ranking_before(
            league_id, match.away_team_id, prediction_time
        )
        
        if home_ranking:
            features["home_rank"] = float(home_ranking["rank"])
            features["home_points"] = float(home_ranking["points"])
        else:
            features["home_rank"] = 0.0
            features["home_points"] = 0.0
        
        if away_ranking:
            features["away_rank"] = float(away_ranking["rank"])
            features["away_points"] = float(away_ranking["points"])
        else:
            features["away_rank"] = 0.0
            features["away_points"] = 0.0
        
        # Derived ranking features
        features["rank_diff"] = features["home_rank"] - features["away_rank"]
        features["points_diff"] = features["home_points"] - features["away_points"]
        
        # --- Form features (temporal) ---
        if include_form:
            home_form = self.temporal.get_team_form_before(
                league_id, match.home_team_id, prediction_time, n_matches=form_window
            )
            away_form = self.temporal.get_team_form_before(
                league_id, match.away_team_id, prediction_time, n_matches=form_window
            )
            
            features["home_form_points"] = float(home_form["form_points"])
            features["home_form_wins"] = float(home_form["form_wins"])
            features["home_form_draws"] = float(home_form["form_draws"])
            features["home_form_losses"] = float(home_form["form_losses"])
            features["home_form_goals_for"] = float(home_form["form_goals_for"])
            features["home_form_goals_against"] = float(home_form["form_goals_against"])
            features["home_form_clean_sheets"] = float(home_form["form_clean_sheets"])
            
            features["away_form_points"] = float(away_form["form_points"])
            features["away_form_wins"] = float(away_form["form_wins"])
            features["away_form_draws"] = float(away_form["form_draws"])
            features["away_form_losses"] = float(away_form["form_losses"])
            features["away_form_goals_for"] = float(away_form["form_goals_for"])
            features["away_form_goals_against"] = float(away_form["form_goals_against"])
            features["away_form_clean_sheets"] = float(away_form["form_clean_sheets"])
            
            # Derived form features
            features["form_points_diff"] = features["home_form_points"] - features["away_form_points"]
            features["form_goals_for_diff"] = features["home_form_goals_for"] - features["away_form_goals_for"]
            features["form_goals_against_diff"] = features["home_form_goals_against"] - features["away_form_goals_against"]
        else:
            # Fill with zeros
            for prefix in ["home", "away"]:
                for suffix in ["form_points", "form_wins", "form_draws", "form_losses",
                               "form_goals_for", "form_goals_against", "form_clean_sheets"]:
                    features[f"{prefix}_{suffix}"] = 0.0
            features["form_points_diff"] = 0.0
            features["form_goals_for_diff"] = 0.0
            features["form_goals_against_diff"] = 0.0
        
        return features

    def build_features_for_completed_match(
        self,
        match_id: int,
        league_id: int,
        form_window: int = 5,
    ) -> Optional[Dict[str, float]]:
        """
        Build features for a completed match using prediction_time = scheduled_at.
        
        This simulates what features would have been available at kickoff time.
        Returns None if the match has no scheduled_at or is not completed.
        """
        match = self.session.get(Match, match_id)
        if not match:
            return None
        
        if match.status != "COMPLETED":
            logger.warning(f"Match {match_id} is not completed (status={match.status})")
            return None
        
        # Use scheduled_at as prediction_time — this is when we would have predicted
        prediction_time = match.scheduled_at
        if not prediction_time:
            logger.warning(f"Match {match_id} has no scheduled_at — cannot build temporal features")
            return None
        
        features = self.build_prediction_features(
            match_id=match_id,
            prediction_time=prediction_time,
            league_id=league_id,
            include_form=True,
            form_window=form_window,
        )
        
        # Add actual result for training
        features["result"] = match.result
        features["home_score"] = float(match.home_score or 0)
        features["away_score"] = float(match.away_score or 0)
        
        return features

    def build_training_dataset(
        self,
        league_id: int,
        form_window: int = 5,
    ) -> List[Dict[str, float]]:
        """
        Build a training dataset from all completed matches.
        
        Each match's features are built using temporal constraints
        (prediction_time = scheduled_at).
        """
        from sqlalchemy import select
        
        completed = self.session.execute(
            select(Match).filter(
                Match.league_id == league_id,
                Match.status == "COMPLETED",
                Match.scheduled_at.isnot(None),
            ).order_by(Match.scheduled_at.asc())
        ).scalars().all()
        
        dataset = []
        for match in completed:
            features = self.build_features_for_completed_match(
                match_id=match.id,
                league_id=league_id,
                form_window=form_window,
            )
            if features:
                dataset.append(features)
        
        logger.info(f"Built training dataset: {len(dataset)} samples from {len(completed)} completed matches")
        return dataset

    def get_feature_names(self, include_form: bool = True) -> List[str]:
        """
        Return an ordered list of feature names.
        Useful for creating DataFrames and ensuring consistent feature ordering.
        """
        features = [
            # Identity
            "home_team_id", "away_team_id", "round_number",
            # Odds (opening)
            "opening_home_odds", "opening_draw_odds", "opening_away_odds",
            # Odds (latest)
            "latest_home_odds", "latest_draw_odds", "latest_away_odds",
            # Odds movement
            "odds_home_movement", "odds_draw_movement", "odds_away_movement",
            # Market implied (opening)
            "market_open_implied_home", "market_open_implied_draw", "market_open_implied_away",
            # Market implied (latest)
            "market_latest_implied_home", "market_latest_implied_draw", "market_latest_implied_away",
            # Overround
            "market_open_overround", "market_latest_overround",
            # Snapshot count
            "n_snapshots",
            # Ranking
            "home_rank", "home_points", "away_rank", "away_points",
            "rank_diff", "points_diff",
        ]
        
        if include_form:
            for prefix in ["home", "away"]:
                features.extend([
                    f"{prefix}_form_points", f"{prefix}_form_wins",
                    f"{prefix}_form_draws", f"{prefix}_form_losses",
                    f"{prefix}_form_goals_for", f"{prefix}_form_goals_against",
                    f"{prefix}_form_clean_sheets",
                ])
            features.extend(["form_points_diff", "form_goals_for_diff", "form_goals_against_diff"])
        
        return features
