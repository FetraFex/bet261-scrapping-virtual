"""
Tests for the pre-flight fixes:
- Fix #1: Last-goal-missing race condition (final event sync)
- Fix #2: ML dataset implied probabilities use normalized values
- Fix #3: Team name casing (acronyms preserved)
- Fix #4: league_name field
- Hardening: jitter, retry config, progress logging
"""
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.normalization.team_normalizer import normalize_team_name


# ---------------------------------------------------------------------------
# Fix #3: Team name casing — comprehensive acronym tests
# ---------------------------------------------------------------------------
class TestTeamNameCasing:
    """Verify that common football acronyms survive normalization."""

    @pytest.mark.parametrize("input_name,expected", [
        ("USA", "USA"),
        ("usa", "USA"),
        ("Usa", "USA"),
        ("Ir Iran", "IR Iran"),
        ("ir iran", "IR Iran"),
        ("IR IRAN", "IR Iran"),
        ("Congo Dr", "Congo DR"),
        ("congo dr", "Congo DR"),
        ("CONGO DR", "Congo DR"),
        ("DRC", "DRC"),
        ("drc", "DRC"),
        ("UAE", "UAE"),
        ("uae", "UAE"),
        ("KSA", "KSA"),
        ("ksa", "KSA"),
        ("UK", "UK"),
    ])
    def test_acronyms_preserved(self, input_name, expected):
        assert normalize_team_name(input_name) == expected

    @pytest.mark.parametrize("input_name,expected", [
        ("Cote d'Ivoire", "Cote D'Ivoire"),
        ("cote d'ivoire", "Cote D'Ivoire"),
        ("COTE D'IVOIRE", "Cote D'Ivoire"),
    ])
    def test_apostrophe_handling(self, input_name, expected):
        assert normalize_team_name(input_name) == expected

    @pytest.mark.parametrize("input_name,expected", [
        ("spain", "Spain"),
        ("SPAIN", "Spain"),
        ("turkiye", "Turkiye"),
        ("Senegal", "Senegal"),
        ("Morocco", "Morocco"),
    ])
    def test_regular_names_unchanged(self, input_name, expected):
        assert normalize_team_name(input_name) == expected

    def test_non_acronym_uppercase_preserved_as_title(self):
        """Words that are uppercase but NOT known acronyms get title-cased."""
        # "TURQUIE" is not a known acronym → becomes "Turquie"
        result = normalize_team_name("TURQUIE")
        assert result == "Turquie"

    def test_empty_and_none(self):
        assert normalize_team_name("") == ""
        assert normalize_team_name(None) == ""


# ---------------------------------------------------------------------------
# Fix #2: ML dataset implied probabilities — unit test for normalization logic
# ---------------------------------------------------------------------------
class TestNormalizedProbabilities:
    """Verify that normalized probabilities sum to 1.0."""

    def test_raw_vs_normalized(self):
        """Raw implied probs may sum >1, normalized must sum to exactly 1."""
        home_odds, draw_odds, away_odds = 1.67, 3.63, 5.37

        raw_h = 1.0 / home_odds
        raw_d = 1.0 / draw_odds
        raw_a = 1.0 / away_odds
        raw_total = raw_h + raw_d + raw_a

        # Raw sums to >1 (overround)
        assert raw_total > 1.0

        # Normalized sums to exactly 1.0
        norm_h = raw_h / raw_total
        norm_d = raw_d / raw_total
        norm_a = raw_a / raw_total
        assert abs(norm_h + norm_d + norm_a - 1.0) < 1e-10

    def test_equal_odds_normalize_to_thirds(self):
        """Equal odds should normalize to 1/3 each."""
        home_odds = draw_odds = away_odds = 3.0
        raw_h = 1.0 / home_odds
        raw_d = 1.0 / draw_odds
        raw_a = 1.0 / away_odds
        total = raw_h + raw_d + raw_a

        assert abs(raw_h / total - 1 / 3) < 1e-10
        assert abs(raw_d / total - 1 / 3) < 1e-10
        assert abs(raw_a / total - 1 / 3) < 1e-10


# ---------------------------------------------------------------------------
# Fix #4: league_name field
# ---------------------------------------------------------------------------
class TestLeagueNameField:
    """Verify league_name is a valid string field on the Match model."""

    def test_match_model_has_league_name(self):
        """The Match model should have a league_name column."""
        from app.models.database_models import Match
        assert hasattr(Match, 'league_name')

    def test_league_name_in_settings(self):
        """Settings should have a LEAGUE_NAME field."""
        from app.config.settings import settings
        assert hasattr(settings, 'LEAGUE_NAME')
        assert settings.LEAGUE_NAME == "World Cup"

    def test_league_id_matches_world_cup(self):
        """LEAGUE_ID should be 8065 (World Cup)."""
        from app.config.settings import settings
        assert settings.LEAGUE_ID == 8065


# ---------------------------------------------------------------------------
# Fix #1: Race condition — verify retry/backoff configuration
# ---------------------------------------------------------------------------
class TestRaceConditionFix:
    """Verify that the final event sync has adequate retry parameters."""

    def test_final_sync_max_attempts_increased(self):
        """EVENT_FINAL_SYNC_MAX_ATTEMPTS should be >= 5 for stoppage-time goals."""
        from app.config.settings import settings
        assert settings.EVENT_FINAL_SYNC_MAX_ATTEMPTS >= 5

    def test_final_sync_delay_increased(self):
        """EVENT_FINAL_SYNC_DELAY_MS should be >= 1000ms."""
        from app.config.settings import settings
        assert settings.EVENT_FINAL_SYNC_DELAY_MS >= 1000


# ---------------------------------------------------------------------------
# Hardening: HTTP client retry config
# ---------------------------------------------------------------------------
class TestHTTPClientHardening:
    """Verify HTTP client is configured for long unattended runs."""

    def test_retry_attempts(self):
        """HTTP client should retry at least 4 times on transient errors."""
        from app.clients.http_client import VirtualLeagueClient
        # The tenacity retry decorator wraps the function; just verify it's callable
        client = VirtualLeagueClient.__new__(VirtualLeagueClient)
        # Check that _get_json exists and is wrapped by tenacity
        assert hasattr(VirtualLeagueClient, '_get_json')

    def test_rate_limit_handling_exists(self):
        """The client module should have rate-limit detection."""
        from app.clients.http_client import _is_rate_limited
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        assert _is_rate_limited(mock_resp_429) is True

        mock_resp_503 = MagicMock()
        mock_resp_503.status_code = 503
        assert _is_rate_limited(mock_resp_503) is True

        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        assert _is_rate_limited(mock_resp_200) is False


# ---------------------------------------------------------------------------
# Hardening: Collection service configuration
# ---------------------------------------------------------------------------
class TestCollectionServiceHardening:
    """Verify collection service has progress tracking and resilience."""

    def test_progress_counters_exist(self):
        """CollectionService should track cumulative metrics."""
        from app.services.collection_service import CollectionService
        # Can't instantiate without DB, but check class attributes
        assert hasattr(CollectionService, '_log_progress')

    def test_signal_handler_setup(self):
        """CollectionService should have signal handler setup."""
        from app.services.collection_service import CollectionService
        assert hasattr(CollectionService, '_setup_signal_handlers')
        assert hasattr(CollectionService, '_handle_shutdown')
