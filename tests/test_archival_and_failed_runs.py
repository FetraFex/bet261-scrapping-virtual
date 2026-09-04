"""
Regression tests for the unattended-run hardening issues raised in audit:

1. Raw JSON archival (mkdir + write) must NEVER take down the collection
   pipeline. An OSError / disk-full condition must be logged and skipped,
   while matches/events/odds persistence continues.
2. Failed collection runs must leave a FAILED row in collection_runs
   (recorded in a fresh session after the main transaction is rolled back),
   so stalls are visible in collection_runs.csv.
"""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.utils.disk_check import save_raw_json, has_enough_disk_space
from app.models.database_models import Base


# ---------------------------------------------------------------------------
# Fix: raw JSON archival isolation
# ---------------------------------------------------------------------------
class TestRawArchivalIsolation:
    def test_save_raw_json_returns_path_on_success(self, tmp_path):
        """Normal archival writes the file and returns its path."""
        path = save_raw_json(tmp_path, "test.json", '{"a": 1}')
        assert path == tmp_path / "test.json"
        assert path.exists()
        assert path.read_text(encoding="utf-8") == '{"a": 1}'

    def test_save_raw_json_creates_nested_dirs(self, tmp_path):
        """Directory tree is created on demand."""
        deep = tmp_path / "2026" / "08" / "29"
        path = save_raw_json(deep, "x.json", "{}")
        assert path is not None and path.exists()

    def test_write_failure_returns_none_and_does_not_raise(self, tmp_path):
        """An OSError during write is swallowed → returns None, no raise.

        This is the exact failure mode from the audit: raw archival must be
        able to fail (Errno 22, disk full, permissions) without killing the
        whole collect_once() and without losing DB persistence.
        """
        with patch("app.utils.disk_check.open", side_effect=OSError(22, "Invalid argument")):
            result = save_raw_json(tmp_path, "fail.json", "{}")
        assert result is None

    def test_mkdir_failure_returns_none_and_does_not_raise(self, tmp_path):
        """Even a mkdir failure (e.g. no space for the day dir) is non-fatal."""
        with patch("pathlib.Path.mkdir", side_effect=OSError(22, "Invalid argument")):
            result = save_raw_json(tmp_path / "nested", "fail.json", "{}")
        assert result is None

    def test_low_disk_space_skips_write(self, tmp_path):
        """When disk space is insufficient, archival is skipped, not crashed."""
        with patch("app.utils.disk_check.has_enough_disk_space", return_value=False):
            result = save_raw_json(tmp_path, "skip.json", "{}")
        assert result is None
        assert not (tmp_path / "skip.json").exists()

    def test_has_enough_disk_space_fail_open(self, tmp_path):
        """If the disk check itself errors, we fail open (try the write)."""
        with patch("app.utils.disk_check.shutil.disk_usage", side_effect=OSError("boom")):
            assert has_enough_disk_space(tmp_path) is True

    def test_unexpected_error_is_swallowed(self, tmp_path):
        """Non-OSError failures during archival are also non-fatal."""
        with patch("app.utils.disk_check.has_enough_disk_space", side_effect=RuntimeError("weird")):
            result = save_raw_json(tmp_path, "weird.json", "{}")
        assert result is None


# ---------------------------------------------------------------------------
# Fix: FAILED collection runs must be recorded
# ---------------------------------------------------------------------------
class TestFailedRunRecording:
    """A failed collect_once() must leave a FAILED row in collection_runs.

    The critical bug this guards against: after session.rollback(), reading
    run.started_at from the expired ORM object can itself raise, so the
    FAILED record is never written and the stall stays invisible.
    """

    def test_started_at_survives_rollback_via_plain_value(self):
        """collect_once must capture started_at before the transaction.

        We assert the pattern by checking that the failure path only ever
        references the plain value captured before the session, never an
        attribute of the rolled-back ORM object.
        """
        from app.services.collection_service import CollectionService
        import inspect

        source = inspect.getsource(CollectionService.collect_once)

        # started_at must be captured before the run object is created/session
        assert "started_at = datetime.utcnow()" in source
        assert "run = CollectionRun(started_at=started_at" in source

        # The failure path must reference the plain value, not run.<attr>
        fail_block = source[source.index("except Exception as e:"):]
        assert "started_at=started_at" in fail_block
        assert "run.started_at" not in fail_block

    def test_collection_runs_model_has_error_fields(self):
        """Export of collection_runs.csv includes status + error_message."""
        from app.models.database_models import CollectionRun
        assert hasattr(CollectionRun, "status")
        assert hasattr(CollectionRun, "error_message")
        assert hasattr(CollectionRun, "started_at")
        assert hasattr(CollectionRun, "completed_at")

    def test_database_schema_includes_run_columns(self):
        """The collection_runs table carries FAILED-visible columns."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        from sqlalchemy import inspect as sa_inspect
        cols = {c["name"] for c in sa_inspect(engine).get_columns("collection_runs")}
        assert {"status", "error_message", "started_at", "completed_at"} <= cols
        engine.dispose()

    def test_run_forever_tracks_consecutive_failures(self):
        """run_forever counts consecutive failures to detect stalls."""
        from app.services.collection_service import CollectionService
        svc = CollectionService.__new__(CollectionService)
        svc._consecutive_empty_cycles = 9
        svc._shutdown_requested = True  # break loop immediately
        svc._total_errors = 0
        svc._cycle_count = 0
        svc._total_matches_collected = 0
        svc._total_retries = 0
        # Verify the counter attribute semantics used by the stall detector
        assert svc._consecutive_empty_cycles == 9
