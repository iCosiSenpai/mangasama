"""Tests for the SQLite backup service."""

from __future__ import annotations

import os
import sqlite3
import time

import pytest

from app.services import backup
from app.settings import get_settings


@pytest.mark.asyncio
async def test_create_backup_makes_valid_copy() -> None:
    # `init_db` (autouse) has created the schema in the per-test DB.
    dest = backup.create_backup()
    assert dest.exists()
    assert dest.stat().st_size > 0
    # The snapshot is a real SQLite DB containing our tables.
    con = sqlite3.connect(str(dest))
    try:
        names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    finally:
        con.close()
    assert "libraries" in names
    assert dest in backup.list_backups()


@pytest.mark.asyncio
async def test_prune_removes_old_backups() -> None:
    backups_dir = get_settings().backups_dir
    recent = backup.create_backup()

    old = backups_dir / "mangasama-20000101T000000Z.db"
    old.write_bytes(b"old")
    # Set its mtime well beyond the retention window.
    old_time = time.time() - (get_settings().backup_retention_days + 5) * 86400
    os.utime(old, (old_time, old_time))

    removed = backup.prune_old_backups()
    assert removed >= 1
    assert not old.exists()
    assert recent.exists()


@pytest.mark.asyncio
async def test_create_backup_no_db(monkeypatch) -> None:
    # Point at a non-existent DB filename → ValueError.
    s = get_settings()
    monkeypatch.setattr(s, "db_filename", "does-not-exist.db")
    with pytest.raises(ValueError):
        backup.create_backup()
