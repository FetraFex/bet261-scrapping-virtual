import pytest
from datetime import datetime, timedelta
from typing import List, Optional


def validate_no_future_features(match_id: int, odds_captured_at: datetime, 
                                 match_completed_at: Optional[datetime]) -> bool:
    """
    Validate that no future features are used in ML dataset.
    Returns True if the feature is safe (no leakage).
    """
    if match_completed_at is None:
        # Match not completed yet, no leakage possible
        return True
    
    # Odds must be captured BEFORE match completion
    return odds_captured_at < match_completed_at


def validate_score_string(score_str: str) -> tuple:
    """Parse and validate a score string like '1:1'."""
    parts = score_str.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid score format: {score_str}")
    
    try:
        home_score = int(parts[0])
        away_score = int(parts[1])
    except ValueError:
        raise ValueError(f"Non-integer scores in: {score_str}")
    
    if home_score < 0 or away_score < 0:
        raise ValueError(f"Negative scores in: {score_str}")
    
    return home_score, away_score


def validate_match_result(home_score: int, away_score: int) -> str:
    """Determine match result from scores."""
    if home_score > away_score:
        return "HOME"
    elif away_score > home_score:
        return "AWAY"
    else:
        return "DRAW"


def detect_temporal_leakage(matches: List[dict]) -> List[dict]:
    """
    Detect temporal leakage in a list of match records.
    Returns list of matches with potential leakage.
    """
    leakage = []
    for match in matches:
        if match.get("status") == "COMPLETED" and match.get("completed_at"):
            completed = datetime.fromisoformat(match["completed_at"])
            odds_captured = datetime.fromisoformat(match.get("odds_captured_at", "2099-01-01"))
            
            if odds_captured > completed:
                leakage.append(match)
    
    return leakage


class TestTemporalLeakage:
    def test_safe_feature(self):
        """Odds captured before match completion is safe."""
        odds_time = datetime(2026, 8, 24, 22, 0, 0)
        match_time = datetime(2026, 8, 24, 23, 0, 0)
        assert validate_no_future_features(1, odds_time, match_time) is True
    
    def test_leaky_feature(self):
        """Odds captured after match completion is leaky."""
        odds_time = datetime(2026, 8, 24, 23, 30, 0)
        match_time = datetime(2026, 8, 24, 23, 0, 0)
        assert validate_no_future_features(1, odds_time, match_time) is False
    
    def test_uncompleted_match(self):
        """Uncompleted match cannot have leakage."""
        odds_time = datetime(2026, 8, 24, 23, 30, 0)
        assert validate_no_future_features(1, odds_time, None) is True
    
    def test_detect_leakage_in_dataset(self):
        """Detect leakage in a list of matches."""
        matches = [
            {
                "id": 1,
                "status": "COMPLETED",
                "completed_at": "2026-08-24T23:00:00",
                "odds_captured_at": "2026-08-24T22:00:00"
            },
            {
                "id": 2,
                "status": "COMPLETED",
                "completed_at": "2026-08-24T23:00:00",
                "odds_captured_at": "2026-08-24T23:30:00"  # LEAKAGE!
            },
            {
                "id": 3,
                "status": "UPCOMING",
                "completed_at": None,
                "odds_captured_at": "2026-08-24T22:00:00"
            }
        ]
        
        leakage = detect_temporal_leakage(matches)
        assert len(leakage) == 1
        assert leakage[0]["id"] == 2


class TestScoreParsing:
    def test_valid_score(self):
        home, away = validate_score_string("1:1")
        assert home == 1
        assert away == 1
    
    def test_zero_score(self):
        home, away = validate_score_string("0:0")
        assert home == 0
        assert away == 0
    
    def test_high_score(self):
        home, away = validate_score_string("5:0")
        assert home == 5
        assert away == 0
    
    def test_invalid_format(self):
        with pytest.raises(ValueError):
            validate_score_string("1-1")
    
    def test_non_numeric(self):
        with pytest.raises(ValueError):
            validate_score_string("a:b")
    
    def test_negative_score(self):
        with pytest.raises(ValueError):
            validate_score_string("-1:1")


class TestMatchResult:
    def test_home_win(self):
        assert validate_match_result(2, 1) == "HOME"
    
    def test_away_win(self):
        assert validate_match_result(1, 3) == "AWAY"
    
    def test_draw(self):
        assert validate_match_result(2, 2) == "DRAW"
    
    def test_zero_zero_draw(self):
        assert validate_match_result(0, 0) == "DRAW"
    
    def test_high_scoring(self):
        assert validate_match_result(6, 0) == "HOME"
