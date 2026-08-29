import json
import pytest
from pathlib import Path
from datetime import datetime

from app.models.schemas import (
    MatchesResponseModel, MatchModel, TeamModel, 
    EventBetTypeModel, EventBetTypeItemModel, RoundModel
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def matches_response():
    with open(FIXTURES_DIR / "matches_response.json") as f:
        return json.load(f)

@pytest.fixture
def results_response():
    with open(FIXTURES_DIR / "results_response.json") as f:
        return json.load(f)

@pytest.fixture
def ranking_response():
    with open(FIXTURES_DIR / "ranking_response.json") as f:
        return json.load(f)

@pytest.fixture
def playout_response():
    with open(FIXTURES_DIR / "playout_response.json") as f:
        return json.load(f)


class TestMatchesSchema:
    def test_parse_matches_response(self, matches_response):
        """Test that matches API response can be parsed into Pydantic model."""
        model = MatchesResponseModel(**matches_response)
        assert len(model.rounds) == 2
        assert model.rounds[0].roundNumber == 87
        assert len(model.rounds[0].matches) == 2
    
    def test_parse_match_model(self, matches_response):
        """Test parsing a single match."""
        match_data = matches_response["rounds"][0]["matches"][0]
        match = MatchModel(**match_data)
        assert match.id == 76827355
        assert match.name == "Turkiye vs Senegal"
        assert match.homeTeam.name == "Turkiye"
        assert match.awayTeam.name == "Senegal"
    
    def test_parse_odds(self, matches_response):
        """Test parsing odds from eventBetTypeItems."""
        match_data = matches_response["rounds"][0]["matches"][0]
        match = MatchModel(**match_data)
        
        assert len(match.eventBetTypes) == 1
        bt = match.eventBetTypes[0]
        assert bt.name == "1X2"
        assert len(bt.eventBetTypeItems) == 3
        
        # Check odds values
        odds_map = {item.shortName: item.odds for item in bt.eventBetTypeItems}
        assert odds_map["1"] == 1.67
        assert odds_map["X"] == 3.63
        assert odds_map["2"] == 5.37
    
    def test_future_round_has_empty_matches(self, matches_response):
        """Test that future rounds have empty matches list."""
        model = MatchesResponseModel(**matches_response)
        future_round = model.rounds[1]
        assert future_round.roundNumber == 88
        assert len(future_round.matches) == 0
    
    def test_empty_event_bet_types(self, matches_response):
        """Test match with no event bet types."""
        match_data = matches_response["rounds"][0]["matches"][1]
        match = MatchModel(**match_data)
        assert match.id == 76827356
        assert len(match.eventBetTypes) == 0


class TestResultsParsing:
    """Test parsing of results API response structure."""
    
    def test_results_score_parsing(self, results_response):
        """Test that score strings like '1:1' can be parsed."""
        for round_data in results_response.get("rounds", []):
            for match in round_data.get("matches", []):
                score_str = match.get("score", "0:0")
                parts = score_str.split(":")
                assert len(parts) == 2
                home_score = int(parts[0])
                away_score = int(parts[1])
                assert isinstance(home_score, int)
                assert isinstance(away_score, int)
    
    def test_results_half_time_score(self, results_response):
        """Test that half-time score is available."""
        match = results_response["rounds"][0]["matches"][0]
        ht_score = match.get("halfTimeScore", "0:0")
        parts = ht_score.split(":")
        assert len(parts) == 2
    
    def test_results_goals_array(self, results_response):
        """Test that goals array is present with minute and team."""
        match = results_response["rounds"][0]["matches"][0]
        goals = match.get("goals", [])
        assert len(goals) == 2
        assert goals[0]["minute"] == 87
        assert goals[0]["team"] == "Home"
        assert goals[1]["team"] == "Away"
    
    def test_results_id_always_zero(self, results_response):
        """Test that results API id is always 0."""
        for round_data in results_response.get("rounds", []):
            for match in round_data.get("matches", []):
                assert match["id"] == 0
                assert match["entryPointId"] == 0


class TestRankingParsing:
    def test_parse_ranking_response(self, ranking_response):
        """Test ranking API response parsing."""
        teams = ranking_response.get("teams", [])
        assert len(teams) == 3
        assert teams[0]["name"] == "Spain"
        assert teams[0]["position"] == 1
        assert teams[0]["points"] == 32
    
    def test_form_history(self, ranking_response):
        """Test form history parsing."""
        team = ranking_response["teams"][0]
        history = team.get("history", [])
        assert len(history) == 5
        assert history[0] == "Draw"
        assert all(h in ["Won", "Lost", "Draw"] for h in history)


class TestPlayoutParsing:
    def test_parse_playout_response(self, playout_response):
        """Test playout API response parsing."""
        matches = playout_response.get("matches", [])
        assert len(matches) == 1
        match = matches[0]
        assert match["id"] == 76827355
        assert len(match["goals"]) == 2
    
    def test_goal_details(self, playout_response):
        """Test goal minute and score details."""
        goal = playout_response["matches"][0]["goals"][0]
        assert goal["minute"] == 27
        assert goal["homeScore"] == 1.0
        assert goal["awayScore"] == 0.0
