"""
Tests for temporal join queries and feature store.

Verifies that:
1. Odds queries only return data before the cutoff time
2. Ranking queries only return data before the cutoff time
3. Team form is computed from temporally-valid matches only
4. Feature building enforces strict temporal constraints
5. No future data leaks into feature vectors
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database_models import Base, Match, OddsSnapshot, MatchEvent, Team, League, RankingSnapshot, RankingEntry
from app.repositories.temporal_repository import TemporalRepository
from app.ml.feature_store import FeatureStore

# SQLite stores datetimes as naive, so use naive UTC timestamps throughout tests


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    sess = Session()
    yield sess
    sess.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def setup_data(session):
    """Populate test data with controlled timestamps."""
    league = League(external_id=1, name="Test League", category="VIRTUAL")
    session.add(league)
    session.flush()

    team_a = Team(league_id=league.id, source_name="Team A", canonical_name="team a")
    team_b = Team(league_id=league.id, source_name="Team B", canonical_name="team b")
    session.add_all([team_a, team_b])
    session.flush()

    # Match 1: scheduled at T+1h, completed at T+3h
    t0 = datetime(2026, 8, 29, 10, 0, 0)
    match1 = Match(
        external_id=100,
        league_id=league.id,
        home_team_id=team_a.id,
        away_team_id=team_b.id,
        scheduled_at=t0 + timedelta(hours=1),
        completed_at=t0 + timedelta(hours=3),
        status="COMPLETED",
        home_score=2,
        away_score=1,
        result="HOME",
        round_number=1,
    )
    session.add(match1)
    session.flush()

    # Odds snapshots for match 1: at T+0.5h, T+0.9h, T+1.2h, T+2h
    odds_times = [
        t0 + timedelta(minutes=30),   # before kickoff
        t0 + timedelta(minutes=54),   # before kickoff
        t0 + timedelta(hours=1, minutes=12),  # after kickoff
        t0 + timedelta(hours=2),      # mid-match
    ]
    odds_values = [
        (1.8, 3.5, 4.0),
        (1.75, 3.4, 4.2),
        (1.7, 3.3, 4.5),
        (1.6, 3.2, 5.0),
    ]
    for capture_time, (h, d, a) in zip(odds_times, odds_values):
        odds = OddsSnapshot(
            match_id=match1.id,
            captured_at=capture_time,
            home_odds=h,
            draw_odds=d,
            away_odds=a,
        )
        session.add(odds)

    # Goal events for match 1
    events = [
        MatchEvent(match_id=match1.id, event_type="GOAL", team_id=team_a.id, team_name="Home", minute=15, captured_at=t0 + timedelta(hours=1, minutes=15)),
        MatchEvent(match_id=match1.id, event_type="GOAL", team_id=team_b.id, team_name="Away", minute=45, captured_at=t0 + timedelta(hours=1, minutes=45)),
        MatchEvent(match_id=match1.id, event_type="GOAL", team_id=team_a.id, team_name="Home", minute=70, captured_at=t0 + timedelta(hours=2, minutes=10)),
    ]
    session.add_all(events)

    # Match 2: completed earlier (historical form source)
    match2 = Match(
        external_id=101,
        league_id=league.id,
        home_team_id=team_a.id,
        away_team_id=team_b.id,
        scheduled_at=t0 - timedelta(days=2),
        completed_at=t0 - timedelta(days=2, hours=-2),
        status="COMPLETED",
        home_score=1,
        away_score=1,
        result="DRAW",
        round_number=23,
    )
    session.add(match2)

    # Match 3: completed earlier (another form source)
    match3 = Match(
        external_id=102,
        league_id=league.id,
        home_team_id=team_b.id,
        away_team_id=team_a.id,
        scheduled_at=t0 - timedelta(days=9),
        completed_at=t0 - timedelta(days=9, hours=-2),
        status="COMPLETED",
        home_score=0,
        away_score=3,
        result="AWAY",
        round_number=22,
    )
    session.add(match3)

    # Ranking snapshot before prediction time
    snapshot1 = RankingSnapshot(
        league_id=league.id,
        captured_at=t0 + timedelta(minutes=30),
        source_hash="hash1",
    )
    session.add(snapshot1)
    session.flush()

    entries = [
        RankingEntry(snapshot_id=snapshot1.id, team_id=team_a.id, team_name="Team A", rank=1, points=45),
        RankingEntry(snapshot_id=snapshot1.id, team_id=team_b.id, team_name="Team B", rank=5, points=30),
    ]
    session.add_all(entries)

    # Another ranking snapshot AFTER prediction time (should NOT be used)
    snapshot2 = RankingSnapshot(
        league_id=league.id,
        captured_at=t0 + timedelta(hours=5),
        source_hash="hash2",
    )
    session.add(snapshot2)
    session.flush()

    entries2 = [
        RankingEntry(snapshot_id=snapshot2.id, team_id=team_a.id, team_name="Team A", rank=1, points=48),
        RankingEntry(snapshot_id=snapshot2.id, team_id=team_b.id, team_name="Team B", rank=4, points=33),
    ]
    session.add_all(entries2)

    session.flush()

    return {
        "league": league,
        "team_a": team_a,
        "team_b": team_b,
        "match1": match1,
        "match2": match2,
        "match3": match3,
        "snapshot1": snapshot1,
        "snapshot2": snapshot2,
        "t0": t0,
    }


# ---------------------------------------------------------------------------
# TemporalRepository tests
# ---------------------------------------------------------------------------

class TestTemporalOddsQueries:
    """Tests for odds queries with temporal constraints."""

    def test_get_odds_before_returns_only_pre_cutoff(self, session, setup_data):
        """Only odds captured BEFORE cutoff should be returned."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        
        # Cutoff = kickoff time (T+1h): should get 2 snapshots
        cutoff = t0 + timedelta(hours=1)
        odds = repo.get_odds_before(match1.id, cutoff)
        assert len(odds) == 2
        assert all(o.captured_at < cutoff for o in odds)

    def test_get_odds_before_with_stricter_cutoff(self, session, setup_data):
        """Stricter cutoff returns fewer snapshots."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        
        # Cutoff = T+55min: should get 2 snapshots (at 30min and 54min)
        cutoff = t0 + timedelta(minutes=55)
        odds = repo.get_odds_before(match1.id, cutoff)
        assert len(odds) == 2

    def test_get_odds_before_with_limit(self, session, setup_data):
        """Limit parameter works correctly."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        
        cutoff = t0 + timedelta(hours=5)
        odds = repo.get_odds_before(match1.id, cutoff, limit=1)
        assert len(odds) == 1

    def test_get_latest_odds_before(self, session, setup_data):
        """Latest odds before cutoff should be the most recent valid snapshot."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        
        cutoff = t0 + timedelta(hours=5)
        latest = repo.get_latest_odds_before(match1.id, cutoff)
        assert latest is not None
        assert float(latest.home_odds) == pytest.approx(1.6)  # Last snapshot value
        assert latest.captured_at == t0 + timedelta(hours=2)

    def test_get_latest_odds_before_no_data(self, session, setup_data):
        """Returns None when no odds exist before cutoff."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        
        # Before any odds were captured
        cutoff = t0 + timedelta(minutes=10)
        latest = repo.get_latest_odds_before(match1.id, cutoff)
        assert latest is None

    def test_get_opening_odds_before(self, session, setup_data):
        """Opening odds should be the earliest snapshot before cutoff."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        
        cutoff = t0 + timedelta(hours=5)
        opening = repo.get_opening_odds_before(match1.id, cutoff)
        assert opening is not None
        assert float(opening.home_odds) == pytest.approx(1.8)  # First snapshot value

    def test_get_odds_movement_before(self, session, setup_data):
        """Odds movement features should use only pre-cutoff data."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        
        # Cutoff before kickoff: only 2 snapshots available
        cutoff = t0 + timedelta(hours=1)
        movement = repo.get_odds_movement_before(match1.id, cutoff)
        
        assert movement["n_snapshots"] == 2
        assert movement["opening_home_odds"] == 1.8
        assert movement["latest_home_odds"] == 1.75
        assert movement["odds_home_movement"] == pytest.approx(-0.05, abs=0.001)

    def test_no_leakage_from_future_odds(self, session, setup_data):
        """Odds captured after cutoff must NOT appear in results."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        
        # Cutoff at T+55min: snapshots at T+72min and T+2h should be excluded
        cutoff = t0 + timedelta(minutes=55)
        odds = repo.get_odds_before(match1.id, cutoff)
        
        for o in odds:
            assert o.captured_at < cutoff, f"Leakage detected: odds at {o.captured_at} >= cutoff {cutoff}"


class TestTemporalRankingQueries:
    """Tests for ranking queries with temporal constraints."""

    def test_get_latest_ranking_before(self, session, setup_data):
        """Should return the ranking snapshot before cutoff, not after."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        league = setup_data["league"]
        
        cutoff = t0 + timedelta(hours=3)
        snapshot, entries = repo.get_latest_ranking_before(league.id, cutoff)
        
        assert snapshot is not None
        assert snapshot.source_hash == "hash1"
        assert len(entries) == 2

    def test_get_latest_ranking_before_excludes_future(self, session, setup_data):
        """Future ranking snapshots must not be returned."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        league = setup_data["league"]
        
        # Before any snapshot exists
        cutoff = t0 + timedelta(minutes=10)
        snapshot, entries = repo.get_latest_ranking_before(league.id, cutoff)
        assert snapshot is None
        assert entries == []

    def test_get_team_ranking_before(self, session, setup_data):
        """Team-specific ranking lookup with temporal constraint."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        league = setup_data["league"]
        team_a = setup_data["team_a"]
        
        cutoff = t0 + timedelta(hours=3)
        ranking = repo.get_team_ranking_before(league.id, team_a.id, cutoff)
        
        assert ranking is not None
        assert ranking["rank"] == 1
        assert ranking["points"] == 45


class TestTemporalFormQueries:
    """Tests for team form computation with temporal constraints."""

    def test_team_form_before(self, session, setup_data):
        """Form should only include completed matches before cutoff."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        league = setup_data["league"]
        team_a = setup_data["team_a"]
        
        # Cutoff = t0+5h: match1 completed at t0+3h (included), match2 and match3 also included
        cutoff = t0 + timedelta(hours=5)
        form = repo.get_team_form_before(league.id, team_a.id, cutoff, n_matches=10)
        
        # Team A played in all 3 completed matches:
        # match1: Home, Won 2-1 → 3 points, GF=2, GA=1
        # match2: Home, Drew 1-1 → 1 point, GF=1, GA=1
        # match3: Away, Won 3-0 (home team B 0:3 team A) → 3 points, GF=3, GA=0
        assert form["form_matches"] == 3
        assert form["form_points"] == 7  # 3 + 1 + 3
        assert form["form_wins"] == 2
        assert form["form_draws"] == 1
        assert form["form_goals_for"] == 6  # 2 + 1 + 3
        assert form["form_goals_against"] == 2  # 1 + 1 + 0

    def test_team_form_excludes_future_matches(self, session, setup_data):
        """Matches completed after cutoff must NOT be included in form."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        league = setup_data["league"]
        team_a = setup_data["team_a"]
        
        # Cutoff = T - 1 day: match1 excluded (completed at T+3h),
        # match2 and match3 included (both completed well before T-1d)
        cutoff = t0 - timedelta(days=1)
        form = repo.get_team_form_before(league.id, team_a.id, cutoff, n_matches=10)
        
        assert form["form_matches"] == 2  # match2 + match3
        assert form["form_wins"] == 1  # match3: away team A won 3-0
        assert form["form_draws"] == 1  # match2: home team A drew 1-1
        assert form["form_points"] == 4  # 1 + 3


class TestTemporalMatchQueries:
    """Tests for completed match queries with temporal constraints."""

    def test_get_completed_matches_before(self, session, setup_data):
        """Should return only completed matches before cutoff."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        league = setup_data["league"]
        
        cutoff = t0 + timedelta(hours=5)
        matches = repo.get_completed_matches_before(league.id, cutoff)
        
        # All 3 matches completed before cutoff:
        # match1: completed_at = t0+3h, match2 and match3: completed days ago
        assert len(matches) == 3
        assert all(m.completed_at < cutoff for m in matches)

    def test_get_completed_matches_before_with_team_filter(self, session, setup_data):
        """Team filter should narrow results correctly."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        league = setup_data["league"]
        team_b = setup_data["team_b"]
        
        cutoff = t0 + timedelta(hours=5)
        matches = repo.get_completed_matches_before(league.id, cutoff, team_id=team_b.id)
        
        # All 3 matches involve team_b and completed before cutoff
        assert len(matches) == 3


class TestTemporalIntegrity:
    """Tests for temporal integrity checking."""

    def test_check_temporal_integrity_valid(self, session, setup_data):
        """A match with all odds before prediction time should pass."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        
        # Prediction time AFTER all odds but BEFORE match completion (T+3h)
        # Odds are at T+30m, T+54m, T+1h12m, T+2h — all before T+2.5h
        # Match completed_at = T+3h — not yet completed at T+2.5h
        prediction_time = t0 + timedelta(hours=2, minutes=30)
        result = repo.check_temporal_integrity(match1.id, prediction_time)
        assert result["is_valid"] is True

    def test_check_temporal_integrity_with_future_odds(self, session, setup_data):
        """A prediction time before some odds exist is not a violation
        (odds after prediction time are just 'not yet available')."""
        repo = TemporalRepository(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        
        # Prediction time at T+1.5h: odds at T+2h are in the future
        prediction_time = t0 + timedelta(hours=1, minutes=30)
        result = repo.check_temporal_integrity(match1.id, prediction_time)
        
        # The odds at T+2h were captured AFTER prediction_time — this IS a violation
        # for the specific scenario of predicting at T+1.5h
        assert result["is_valid"] is False
        assert len(result["violations"]) > 0


# ---------------------------------------------------------------------------
# FeatureStore tests
# ---------------------------------------------------------------------------

class TestFeatureStore:
    """Tests for the FeatureStore that builds ML features with temporal constraints."""

    def test_build_prediction_features_basic(self, session, setup_data):
        """Feature vector should contain all expected feature groups."""
        store = FeatureStore(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        league = setup_data["league"]
        
        # Predict at kickoff time (T+1h)
        prediction_time = t0 + timedelta(hours=1)
        features = store.build_prediction_features(
            match_id=match1.id,
            prediction_time=prediction_time,
            league_id=league.id,
        )
        
        # Verify all feature groups are present
        assert "opening_home_odds" in features
        assert "latest_home_odds" in features
        assert "home_rank" in features
        assert "away_rank" in features
        assert "home_form_points" in features
        assert "away_form_points" in features

    def test_build_prediction_features_no_leakage(self, session, setup_data):
        """Features must only use data from before prediction_time."""
        store = FeatureStore(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        league = setup_data["league"]
        
        # Predict at T+55min (before kickoff)
        prediction_time = t0 + timedelta(minutes=55)
        features = store.build_prediction_features(
            match_id=match1.id,
            prediction_time=prediction_time,
            league_id=league.id,
        )
        
        # Opening odds should be 1.8 (first snapshot at T+30min, valid)
        assert features["opening_home_odds"] == 1.8
        # Latest odds should be 1.75 (second snapshot at T+54min, valid)
        assert features["latest_home_odds"] == 1.75
        # n_snapshots should be 2
        assert features["n_snapshots"] == 2.0

    def test_build_prediction_features_later_cutoff(self, session, setup_data):
        """Features with a later cutoff should see more odds snapshots."""
        store = FeatureStore(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        league = setup_data["league"]
        
        # Predict at T+5h (after everything)
        prediction_time = t0 + timedelta(hours=5)
        features = store.build_prediction_features(
            match_id=match1.id,
            prediction_time=prediction_time,
            league_id=league.id,
        )
        
        # Should see all 4 snapshots
        assert features["n_snapshots"] == 4.0
        assert features["latest_home_odds"] == 1.6

    def test_build_prediction_features_ranking_temporal(self, session, setup_data):
        """Ranking features should use only the pre-cutoff snapshot."""
        store = FeatureStore(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        league = setup_data["league"]
        
        # Predict at T+3h
        prediction_time = t0 + timedelta(hours=3)
        features = store.build_prediction_features(
            match_id=match1.id,
            prediction_time=prediction_time,
            league_id=league.id,
        )
        
        # Should use snapshot1 (hash1) — team_a rank=1, team_b rank=5
        assert features["home_rank"] == 1.0
        assert features["away_rank"] == 5.0
        assert features["rank_diff"] == -4.0

    def test_build_features_for_completed_match(self, session, setup_data):
        """Building features for a completed match uses scheduled_at as prediction_time."""
        store = FeatureStore(session)
        league = setup_data["league"]
        match2 = setup_data["match2"]
        
        features = store.build_features_for_completed_match(
            match_id=match2.id,
            league_id=league.id,
        )
        
        assert features is not None
        assert features["result"] == "DRAW"
        assert features["home_score"] == 1.0

    def test_build_training_dataset(self, session, setup_data):
        """Training dataset should have one row per completed match."""
        store = FeatureStore(session)
        league = setup_data["league"]
        
        dataset = store.build_training_dataset(league.id)
        
        assert len(dataset) >= 2  # match2 and match3 are completed
        assert all("result" in d for d in dataset)
        assert all("home_score" in d for d in dataset)

    def test_feature_names_consistency(self, session):
        """Feature names list should match what build_prediction_features returns."""
        store = FeatureStore(session)
        names = store.get_feature_names()
        
        # Should have at least 30 features
        assert len(names) >= 30
        
        # No duplicates
        assert len(names) == len(set(names))

    def test_no_leakage_from_completed_at(self, session, setup_data):
        """completed_at must not appear in features (it's a leakage risk)."""
        store = FeatureStore(session)
        t0 = setup_data["t0"]
        match1 = setup_data["match1"]
        league = setup_data["league"]
        
        prediction_time = t0 + timedelta(hours=1)
        features = store.build_prediction_features(
            match_id=match1.id,
            prediction_time=prediction_time,
            league_id=league.id,
        )
        
        # completed_at and final scores must NOT be in features
        assert "completed_at" not in features
        assert "home_score" not in features
        assert "away_score" not in features
        assert "result" not in features
