"""SQLite backup service.

The DB runs in WAL mode, so a plain file copy could miss data sitting in
the `-wal` file. We use SQLite's online backup API
(`Connection.backup`), which produces a consistent snapshot. Backups are
written to `<config>/backups/mangasama-<UTCts>.db` and pruned by age.

`create_backup` is synchronous (sqlite3 is blocking); async callers wrap
it in `asyncio.to_thread`.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import structlog

from app.settings import get_settings

logger = structlog.get_logger("mangasama.services.backup")

_PATTERN = "mangasama-*.db"


def _db_path() -> Path:
    s = get_settings()
    return s.data_dir / s.db_filename


def list_backups() -> list[Path]:
    return sorted(get_settings().backups_dir.glob(_PATTERN))


def prune_old_backups() -> int:
    """Delete backups older than `backup_retention_days`. Returns the count removed."""
    cutoff = time.time() - get_settings().backup_retention_days * 86400
    removed = 0
    for p in list_backups():
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def create_backup() -> Path:
    """Write a WAL-safe snapshot of the DB and prune old ones. Returns the path."""
    src = _db_path()
    if not src.exists():
        raise ValueError(f"no database to back up at {src}")
    dest_dir = get_settings().backups_dir  # property mkdirs it
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_dir / f"mangasama-{ts}.db"

    src_con = sqlite3.connect(str(src))
    try:
        dst_con = sqlite3.connect(str(dest))
        try:
            src_con.backup(dst_con)
        finally:
            dst_con.close()
    finally:
        src_con.close()

    removed = prune_old_backups()
    logger.info("backup.created", path=str(dest), size=dest.stat().st_size, pruned=removed)
    return dest


__all__ = ["create_backup", "list_backups", "prune_old_backups"]
