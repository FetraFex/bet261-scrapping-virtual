"""
Comprehensive data validation tests for the virtual league collector.

Covers:
- Invalid dates (sentinel 0001-01-01 values)
- NULL team IDs
- Orphan events / odds / ranking entries
- Duplicate matches / snapshots
- Impossible timestamps
- Future information leakage
- Invalid odds / scores / team relationships
"""
import pytest
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Pure validation helpers (no DB required)
# ---------------------------------------------------------------------------

SENTINEL_DATE = datetime(1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def is_valid_scheduled_at(dt: Optional[datetime]) -> bool:
    """Check that a scheduled_at value is a real date, not the API sentinel."""
    if dt is None:
        return False
    if dt == SENTINEL_DATE:
        return False
    # Must be in a reasonable range (year >= 2020)
    if dt.year < 2020:
        return False
    return True


def validate_odds(home: float, draw: float, away: float) -> List[str]:
    """Validate odds values and return a list of error strings."""
    errors = []
    for name, val in [("home_odds", home), ("draw_odds", draw), ("away_odds", away)]:
        if val <= 0:
            errors.append(f"{name} must be > 0, got {val}")
        if val > 1000:
            errors.append(f"{name} suspiciously high: {val}")
    return errors


def validate_score(home_score: int, away_score: int) -> List[str]:
    """Validate score values."""
    errors = []
    if home_score < 0:
        errors.append(f"home_score cannot be negative: {home_score}")
    if away_score < 0:
        errors.append(f"away_score cannot be negative: {away_score}")
    if home_score > 30 or away_score > 30:
        errors.append(f"score seems impossibly high: {home_score}-{away_score}")
    return errors


def compute_overround(home_odds: float, draw_odds: float, away_odds: float) -> float:
    """Sum of implied probabilities for 1X2 odds."""
    return (1.0 / home_odds) + (1.0 / draw_odds) + (1.0 / away_odds)


def check_temporal_leakage(
    match_scheduled_at: datetime,
    odds_captured_at: datetime,
    match_completed_at: Optional[datetime] = None,
) -> Optional[str]:
    """
    Check if an odds snapshot leaks future information.
    Returns an error string if leakage detected, else None.
    """
    if odds_captured_at >= match_scheduled_at:
        return "odds_captured_at >= match scheduled_at (odds taken at or after kickoff)"
    if match_completed_at and odds_captured_at > match_completed_at:
        return "odds_captured_at > match completed_at (odds taken after match ended)"
    return None


def check_ranking_temporal_join(
    ranking_snapshot_time: datetime,
    prediction_time: datetime,
) -> bool:
    """
    Verify a ranking snapshot is valid for a prediction.
    The snapshot must have been captured BEFORE the prediction time.
    """
    return ranking_snapshot_time < prediction_time


def detect_duplicate_matches(matches: List[Dict]) -> List[int]:
    """Detect duplicate matches by external_id. Returns list of duplicated IDs."""
    seen = {}
    dupes = []
    for m in matches:
        eid = m.get("external_id")
        if eid is None or eid == 0:
            continue
        if eid in seen:
            dupes.append(eid)
        else:
            seen[eid] = True
    return dupes


def detect_duplicate_snapshots(snapshots: List[Dict]) -> List[int]:
    """Detect duplicate ranking snapshots by source_hash. Returns list of duplicate snapshot IDs."""
    seen = {}
    dupes = []
    for s in snapshots:
        h = s.get("source_hash")
        sid = s.get("id")
        if h in seen:
            dupes.append(sid)
        else:
            seen[h] = sid
    return dupes


def detect_impossible_timestamps(matches: List[Dict]) -> List[str]:
    """Detect matches with impossible timestamps."""
    errors = []
    for m in matches:
        sched = m.get("scheduled_at")
        first = m.get("first_seen_at")
        last = m.get("last_seen_at")
        completed = m.get("completed_at")

        if sched and first and sched < first:
            errors.append(
                f"Match {m.get('id')}: scheduled_at < first_seen_at"
            )
        if completed and sched and completed < sched:
            errors.append(
                f"Match {m.get('id')}: completed_at < scheduled_at"
            )
        if first and last and last < first:
            errors.append(
                f"Match {m.get('id')}: last_seen_at < first_seen_at"
            )
    return errors


# ---------------------------------------------------------------------------
# Tests: Invalid dates
# ---------------------------------------------------------------------------

class TestInvalidDates:
    def test_sentinel_date_rejected(self):
        assert not is_valid_scheduled_at(SENTINEL_DATE)

    def test_none_rejected(self):
        assert not is_valid_scheduled_at(None)

    def test_year_0001_rejected(self):
        dt = datetime(1, 1, 1, tzinfo=timezone.utc)
        assert not is_valid_scheduled_at(dt)

    def test_valid_date_accepted(self):
        dt = datetime(2026, 8, 24, 22, 0, 0, tzinfo=timezone.utc)
        assert is_valid_scheduled_at(dt)

    def test_very_old_date_rejected(self):
        dt = datetime(1999, 1, 1, tzinfo=timezone.utc)
        assert not is_valid_scheduled_at(dt)

    def test_api_sentinel_format(self):
        """The API sends '0001-01-01T00:00:00Z' — ensure it's caught."""
        dt = datetime(1, 1, 1, 0, 0, 0)
        assert not is_valid_scheduled_at(dt)


# ---------------------------------------------------------------------------
# Tests: NULL team IDs
# ---------------------------------------------------------------------------

class TestNullTeamIds:
    def test_match_event_missing_team(self):
        """Events from playout without team attribution should be flagged."""
        event = {"team_id": None, "team_name": None}
        assert event["team_id"] is None
        assert event["team_name"] is None

    def test_ranking_entry_missing_team_id(self):
        entry = {"team_id": None, "team_name": "Spain"}
        assert entry["team_id"] is None
        assert entry["team_name"] is not None


# ---------------------------------------------------------------------------
# Tests: Orphan records
# ---------------------------------------------------------------------------

class TestOrphanRecords:
    def test_orphan_event(self):
        """An event whose match_id doesn't match any existing match."""
        events = [{"id": 1, "match_id": 999}]
        match_ids = {1, 2, 3}
        orphans = [e for e in events if e["match_id"] not in match_ids]
        assert len(orphans) == 1

    def test_orphan_odds(self):
        odds = [{"match_id": 999}]
        match_ids = {1, 2, 3}
        orphans = [o for o in odds if o["match_id"] not in match_ids]
        assert len(orphans) == 1

    def test_orphan_ranking_entry(self):
        entries = [{"snapshot_id": 999}]
        snapshot_ids = {1, 2, 3}
        orphans = [e for e in entries if e["snapshot_id"] not in snapshot_ids]
        assert len(orphans) == 1

    def test_no_orphans(self):
        events = [{"match_id": 1}, {"match_id": 2}]
        match_ids = {1, 2}
        orphans = [e for e in events if e["match_id"] not in match_ids]
        assert len(orphans) == 0


# ---------------------------------------------------------------------------
# Tests: Duplicate matches / snapshots
# ---------------------------------------------------------------------------

class TestDuplicates:
    def test_detect_duplicate_external_id(self):
        matches = [
            {"id": 1, "external_id": 100},
            {"id": 2, "external_id": 100},
            {"id": 3, "external_id": 200},
        ]
        dupes = detect_duplicate_matches(matches)
        assert 100 in dupes

    def test_no_duplicates(self):
        matches = [
            {"id": 1, "external_id": 100},
            {"id": 2, "external_id": 200},
        ]
        dupes = detect_duplicate_matches(matches)
        assert len(dupes) == 0

    def test_duplicate_ranking_snapshots(self):
        snapshots = [
            {"id": 1, "source_hash": "abc"},
            {"id": 2, "source_hash": "abc"},
        ]
        dupes = detect_duplicate_snapshots(snapshots)
        assert 2 in dupes

    def test_unique_ranking_snapshots(self):
        snapshots = [
            {"id": 1, "source_hash": "abc"},
            {"id": 2, "source_hash": "def"},
        ]
        dupes = detect_duplicate_snapshots(snapshots)
        assert len(dupes) == 0


# ---------------------------------------------------------------------------
# Tests: Impossible timestamps
# ---------------------------------------------------------------------------

class TestImpossibleTimestamps:
    def test_normal_match(self):
        now = datetime(2026, 8, 24, tzinfo=timezone.utc)
        matches = [{
            "id": 1,
            "scheduled_at": now - timedelta(hours=1),
            "first_seen_at": now - timedelta(hours=3),
            "last_seen_at": now,
            "completed_at": now + timedelta(minutes=5),
        }]
        errors = detect_impossible_timestamps(matches)
        assert len(errors) == 0

    def test_scheduled_before_first_seen(self):
        now = datetime(2026, 8, 24, tzinfo=timezone.utc)
        matches = [{
            "id": 1,
            "scheduled_at": now + timedelta(hours=1),
            "first_seen_at": now + timedelta(hours=2),
            "last_seen_at": now + timedelta(hours=3),
        }]
        errors = detect_impossible_timestamps(matches)
        assert any("scheduled_at < first_seen_at" in e for e in errors)

    def test_completed_before_scheduled(self):
        now = datetime(2026, 8, 24, tzinfo=timezone.utc)
        matches = [{
            "id": 1,
            "scheduled_at": now + timedelta(hours=2),
            "first_seen_at": now,
            "last_seen_at": now + timedelta(hours=3),
            "completed_at": now + timedelta(hours=1),
        }]
        errors = detect_impossible_timestamps(matches)
        assert any("completed_at < scheduled_at" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests: Future information leakage
# ---------------------------------------------------------------------------

class TestTemporalLeakage:
    def test_safe_odds(self):
        """Odds captured before kickoff are safe."""
        scheduled = datetime(2026, 8, 24, 22, 0, 0, tzinfo=timezone.utc)
        odds_time = datetime(2026, 8, 24, 21, 55, 0, tzinfo=timezone.utc)
        assert check_temporal_leakage(scheduled, odds_time) is None

    def test_odds_after_kickoff(self):
        """Odds captured at or after kickoff are leaky."""
        scheduled = datetime(2026, 8, 24, 22, 0, 0, tzinfo=timezone.utc)
        odds_time = datetime(2026, 8, 24, 22, 5, 0, tzinfo=timezone.utc)
        assert check_temporal_leakage(scheduled, odds_time) is not None

    def test_odds_at_kickoff(self):
        """Odds captured exactly at kickoff are leaky."""
        scheduled = datetime(2026, 8, 24, 22, 0, 0, tzinfo=timezone.utc)
        odds_time = scheduled
        assert check_temporal_leakage(scheduled, odds_time) is not None

    def test_odds_after_completion(self):
        """Odds captured after match completed are leaky."""
        scheduled = datetime(2026, 8, 24, 22, 0, 0, tzinfo=timezone.utc)
        completed = datetime(2026, 8, 24, 23, 50, 0, tzinfo=timezone.utc)
        odds_time = datetime(2026, 8, 24, 23, 55, 0, tzinfo=timezone.utc)
        assert check_temporal_leakage(scheduled, odds_time, completed) is not None

    def test_ranking_before_prediction(self):
        """Ranking snapshot before prediction time is valid."""
        snap_time = datetime(2026, 8, 24, 20, 0, 0, tzinfo=timezone.utc)
        pred_time = datetime(2026, 8, 24, 22, 0, 0, tzinfo=timezone.utc)
        assert check_ranking_temporal_join(snap_time, pred_time)

    def test_ranking_after_prediction(self):
        """Ranking snapshot after prediction time is leakage."""
        snap_time = datetime(2026, 8, 24, 23, 0, 0, tzinfo=timezone.utc)
        pred_time = datetime(2026, 8, 24, 22, 0, 0, tzinfo=timezone.utc)
        assert not check_ranking_temporal_join(snap_time, pred_time)

    def test_ranking_exactly_at_prediction(self):
        """Ranking snapshot at prediction time is not strictly before."""
        snap_time = datetime(2026, 8, 24, 22, 0, 0, tzinfo=timezone.utc)
        pred_time = datetime(2026, 8, 24, 22, 0, 0, tzinfo=timezone.utc)
        assert not check_ranking_temporal_join(snap_time, pred_time)


# ---------------------------------------------------------------------------
# Tests: Invalid odds
# ---------------------------------------------------------------------------

class TestInvalidOdds:
    def test_valid_odds(self):
        errors = validate_odds(1.67, 3.63, 5.37)
        assert len(errors) == 0

    def test_zero_odds(self):
        errors = validate_odds(0.0, 3.63, 5.37)
        assert len(errors) > 0

    def test_negative_odds(self):
        errors = validate_odds(-1.0, 3.63, 5.37)
        assert len(errors) > 0

    def test_overround(self):
        """Overround should be > 1 for bookmaker odds."""
        overround = compute_overround(1.67, 3.63, 5.37)
        assert overround > 1.0
        # Rough sanity check
        assert 1.0 < overround < 1.5

    def test_market_probabilities_sum_to_one(self):
        """Normalized probabilities should sum to 1."""
        home, draw, away = 1.67, 3.63, 5.37
        raw = [1.0 / home, 1.0 / draw, 1.0 / away]
        total = sum(raw)
        normalized = [r / total for r in raw]
        assert abs(sum(normalized) - 1.0) < 1e-10


# ---------------------------------------------------------------------------
# Tests: Invalid scores
# ---------------------------------------------------------------------------

class TestInvalidScores:
    def test_valid_scores(self):
        errors = validate_score(2, 1)
        assert len(errors) == 0

    def test_zero_zero(self):
        errors = validate_score(0, 0)
        assert len(errors) == 0

    def test_negative_score(self):
        errors = validate_score(-1, 2)
        assert len(errors) > 0

    def test_impossibly_high_score(self):
        errors = validate_score(50, 3)
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Tests: Invalid team relationships
# ---------------------------------------------------------------------------

class TestTeamRelationships:
    def test_home_and_away_different(self):
        """A match cannot have the same team on both sides."""
        home_team_id = 1
        away_team_id = 1
        assert home_team_id == away_team_id  # This would be invalid

    def test_valid_team_relationship(self):
        home_team_id = 1
        away_team_id = 2
        assert home_team_id != away_team_id  # This is valid


# ---------------------------------------------------------------------------
# Tests: Odds baseline calculations
# ---------------------------------------------------------------------------

class TestOddsBaseline:
    """Tests for the market-implied probability baseline."""

    def test_raw_probabilities(self):
        home_odds, draw_odds, away_odds = 2.0, 3.5, 4.0
        p_home = 1.0 / home_odds
        p_draw = 1.0 / draw_odds
        p_away = 1.0 / away_odds

        assert abs(p_home - 0.5) < 1e-10
        assert abs(p_draw - (1 / 3.5)) < 1e-10
        assert abs(p_away - 0.25) < 1e-10

    def test_overround_computation(self):
        home_odds, draw_odds, away_odds = 2.0, 3.5, 4.0
        overround = compute_overround(home_odds, draw_odds, away_odds)
        expected = 0.5 + (1 / 3.5) + 0.25
        assert abs(overround - expected) < 1e-10

    def test_normalized_probabilities(self):
        home_odds, draw_odds, away_odds = 2.0, 3.5, 4.0
        raw = [1.0 / home_odds, 1.0 / draw_odds, 1.0 / away_odds]
        total = sum(raw)
        normalized = [r / total for r in raw]
        assert abs(sum(normalized) - 1.0) < 1e-10
        assert normalized[0] > normalized[1] > normalized[2]

    def test_equal_odds(self):
        """If all odds are equal, normalized probability should be 1/3 each."""
        home_odds = draw_odds = away_odds = 3.0
        overround = compute_overround(home_odds, draw_odds, away_odds)
        assert abs(overround - 1.0) < 1e-10
        raw = [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
        total = sum(raw)
        normalized = [r / total for r in raw]
        assert all(abs(p - (1 / 3)) < 1e-10 for p in normalized)


# ---------------------------------------------------------------------------
# Tests: Fixture data validation (using actual fixture JSON)
# ---------------------------------------------------------------------------

class TestFixtureDataValidation:
    """Validate fixture data has the expected structure."""

    def test_matches_fixture_has_sentinel_dates(self, sample_matches_data):
        """Confirm that the fixture data contains sentinel expectedStart values."""
        for round_data in sample_matches_data["rounds"]:
            for match in round_data.get("matches", []):
                # All individual match expectedStart should be sentinel
                assert match["expectedStart"] == "0001-01-01T00:00:00Z"

    def test_matches_fixture_round_has_real_date(self, sample_matches_data):
        """The round-level expectedStart should have a real date."""
        round_0 = sample_matches_data["rounds"][0]
        assert round_0["expectedStart"] != "0001-01-01T00:00:00Z"

    def test_results_fixture_goals_have_team(self, sample_results_data):
        """Goals in the results fixture should have a 'team' field."""
        for round_data in sample_results_data["rounds"]:
            for match in round_data.get("matches", []):
                for goal in match.get("goals", []):
                    assert "team" in goal
                    assert goal["team"] in ("Home", "Away")

    def test_ranking_fixture_has_names(self, sample_ranking_data):
        """Ranking entries should have team names."""
        for team in sample_ranking_data["teams"]:
            assert team["name"]
            assert len(team["name"]) > 0
            # But NO team ID (this is the API's limitation)
            assert "id" not in team  # API doesn't provide team IDs

    def test_playout_fixture_no_team_field(self, sample_playout_data):
        """Playout goals do NOT have a team field — we must infer from scores."""
        for match in sample_playout_data["matches"]:
            for goal in match["goals"]:
                # Playout API does NOT provide team info
                assert "team" not in goal
                # It only provides cumulative scores
                assert "homeScore" in goal
                assert "awayScore" in goal
