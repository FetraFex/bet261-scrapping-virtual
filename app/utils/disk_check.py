"""Disk space safety check for raw JSON archival.

Raw JSON files are audit-trail only — they are NOT the critical path.
Collection of matches/events/odds/rankings into the database must continue
even when archival cannot be performed (disk full, permission error, etc).

These helpers therefore NEVER raise: they log a warning and return None so
the caller can keep going.
"""
import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Minimum free space to allow raw writes: 100 MB
MIN_FREE_SPACE_MB = 100


def has_enough_disk_space(path: Path) -> bool:
    """Check if the target path has enough free disk space for raw archival.

    Returns True if space is sufficient or if the check fails (fail-open).
    Returns False only if we can confirm there is NOT enough space.
    """
    try:
        usage = shutil.disk_usage(path)
        free_mb = usage.free / (1024 * 1024)
        if free_mb < MIN_FREE_SPACE_MB:
            logger.warning(
                f"Low disk space on {path}: {free_mb:.0f}MB free "
                f"(minimum: {MIN_FREE_SPACE_MB}MB). Skipping raw JSON archival."
            )
            return False
        return True
    except Exception as e:
        # Fail-open: if we can't check, try writing anyway
        logger.debug(f"Could not check disk space: {e}")
        return True


def save_raw_json(directory: Path, filename: str, content: str) -> Optional[Path]:
    """Best-effort raw JSON archival.

    Creates ``directory`` (recursively) and writes ``content`` to
    ``directory / filename``. On ANY failure (disk full, permission error,
    invalid path) logs a warning and returns None — it never raises.

    Returns the saved file path on success, None otherwise.
    """
    try:
        filepath = directory / filename
        if not has_enough_disk_space(directory):
            return None
        directory.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath
    except OSError as e:
        logger.warning(f"Could not save raw JSON to {directory} (non-fatal): {e}")
        return None
    except Exception as e:
        # Never let archival take down the collection pipeline.
        logger.warning(f"Unexpected error saving raw JSON to {directory} (non-fatal): {e}")
        return None
