import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_matches_data():
    """Load sample matches API response."""
    with open(FIXTURES_DIR / "matches_response.json") as f:
        return json.load(f)


@pytest.fixture
def sample_results_data():
    """Load sample results API response."""
    with open(FIXTURES_DIR / "results_response.json") as f:
        return json.load(f)


@pytest.fixture
def sample_ranking_data():
    """Load sample ranking API response."""
    with open(FIXTURES_DIR / "ranking_response.json") as f:
        return json.load(f)


@pytest.fixture
def sample_playout_data():
    """Load sample playout API response."""
    with open(FIXTURES_DIR / "playout_response.json") as f:
        return json.load(f)


@pytest.fixture
def sample_match_record():
    """A sample match record for testing."""
    return {
        "id": 1,
        "external_id": 76827355,
        "league_id": 1,
        "home_team_id": 1,
        "away_team_id": 2,
        "scheduled_at": datetime.utcnow().isoformat(),
        "status": "UPCOMING",
        "home_score": None,
        "away_score": None,
        "result": None
    }


@pytest.fixture
def sample_odds_record():
    """A sample odds snapshot record for testing."""
    return {
        "id": 1,
        "match_id": 1,
        "captured_at": datetime.utcnow().isoformat(),
        "home_odds": 1.67,
        "draw_odds": 3.63,
        "away_odds": 5.37
    }
