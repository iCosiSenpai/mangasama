"""Checkpoint test for Step 2: Alembic migrations.

Verifies:
  - `alembic upgrade head` runs cleanly on a fresh DB
  - All 12 expected tables exist
  - All expected indexes exist
  - All expected unique constraints exist (incl. the critical chapter idempotency key)
  - The 0002 seed actually populated `domain_health` from `config/sources.yaml`
  - `alembic downgrade base` then `upgrade head` is round-trip-safe
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
import yaml
from alembic import command
from alembic.config import Config


# Force a unique DB per test, independent of the conftest autouse fixture,
# so the test is isolated from anything else in the suite.
@pytest.fixture
def alembic_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "manga.db"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DB_FILENAME", "manga.db")

    # Reset the cached settings.
    from app.settings import get_settings
    get_settings.cache_clear()

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")

    yield cfg, db_path

    # Drop alembic_version so the next test starts clean.
    if db_path.exists():
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("DROP TABLE IF EXISTS alembic_version")
            conn.commit()


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }


def _indexes(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND name NOT LIKE 'sqlite_%'",
            (table,),
        ).fetchall()
    }


def _table_sql(conn: sqlite3.Connection, table: str) -> str:
    return (
        conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()[0]
        or ""
    )


def test_alembic_upgrade_creates_all_12_tables(alembic_db) -> None:
    cfg, db_path = alembic_db
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migrations"))
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(db_path)) as conn:
        names = _tables(conn)
    expected = {
        "libraries", "series", "series_external_ids", "series_genres",
        "series_tags", "series_authors", "volumes", "chapters", "pages",
        "follow_log", "provider_jobs", "domain_health",
        # alembic's own bookkeeping table
        "alembic_version",
    }
    missing = expected - names
    assert not missing, f"Missing tables: {missing}\nHave: {sorted(names)}"
    # And we have nothing extra.
    assert (names - expected) == set(), f"Unexpected tables: {names - expected}"


def test_critical_idempotency_unique_constraint(alembic_db) -> None:
    """The (source_provider, source_id, language) unique constraint is what
    prevents the download orchestrator from inserting the same chapter twice.

    It's the single most important constraint in the schema.
    """
    cfg, db_path = alembic_db
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migrations"))
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(db_path)) as conn:
        sql = _table_sql(conn, "chapters")
        # SQLite names unique constraints AUTO_<table>_<n> when the constraint
        # is unnamed, but we explicitly named it. Check both: the name AND
        # the column triplet in the CREATE statement.
        assert "uq_chapter_source_lang" in sql, sql
        assert "source_provider" in sql
        assert "source_id" in sql
        assert "language" in sql

        # And the runtime check: a real duplicate insert is rejected.
        # First insert a parent row.
        with sqlite3.connect(str(db_path)) as conn2:
            conn2.executescript(
                """
                INSERT INTO libraries (id, name, type, root_path, folder_strategy, cover_strategy,
                                       providers, italian_priority, follow_interval_hours, jpg_quality,
                                       deleted, created_at, updated_at)
                VALUES (1, 'L', 'manga', '/tmp', 'series_volume_chapter', 'series_first',
                        '[]', 1, 24, 85, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

                INSERT INTO series (id, library_id, title, alt_titles, source_priority, deleted,
                                    created_at, updated_at)
                VALUES (1, 1, 'S', '[]', '[]', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

                INSERT INTO volumes (id, series_id, number, sort)
                VALUES (1, 1, '1', 1.0);

                INSERT INTO chapters (volume_id, number, sort, source_provider, source_id, language)
                VALUES (1, '1', 1.0, 'mangadex', 'abc', 'it');
                """
            )
            conn2.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO chapters (volume_id, number, sort, source_provider, source_id, language) "
                "VALUES (1, '2', 2.0, 'mangadex', 'abc', 'it')"
            )
            conn.commit()


def test_0002_seeds_domain_health_from_yaml(alembic_db) -> None:
    cfg, db_path = alembic_db
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migrations"))
    command.upgrade(cfg, "head")

    # Load the YAML so we know what we expect to find.
    yaml_path = Path(__file__).resolve().parent.parent / "config" / "sources.yaml"
    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    sources = data.get("sources") or {}

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT source, domain, healthy, fail_count FROM domain_health ORDER BY source, domain"
        ).fetchall()

    # Build the expected set of (source, domain) pairs.
    expected: set[tuple[str, str]] = set()
    for name, cfg_src in sources.items():
        if not cfg_src.get("enabled", True):
            continue
        if cfg_src.get("primary"):
            expected.add((name, cfg_src["primary"]))
        for alt in cfg_src.get("alternates") or []:
            expected.add((name, alt))

    assert expected, "YAML parsing produced an empty set; check the test fixture"
    actual = {(r[0], r[1]) for r in rows}
    assert actual == expected, f"Expected {expected}, got {actual}"
    # And every seeded row is healthy with fail_count=0.
    for r in rows:
        assert r[2] == 1  # SQLite stores bool as int
        assert r[3] == 0


def test_alembic_roundtrip_downgrade_upgrade(alembic_db) -> None:
    """downgrade base -> upgrade head must work without errors."""
    cfg, db_path = alembic_db
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migrations"))

    command.upgrade(cfg, "head")
    with sqlite3.connect(str(db_path)) as conn:
        names_after_up = _tables(conn)
    assert "libraries" in names_after_up

    command.downgrade(cfg, "base")
    with sqlite3.connect(str(db_path)) as conn:
        names_after_down = _tables(conn)
    # Only alembic_version is left after downgrade base.
    assert names_after_down == {"alembic_version"}, f"After downgrade: {names_after_down}"

    command.upgrade(cfg, "head")
    with sqlite3.connect(str(db_path)) as conn:
        names_after_up2 = _tables(conn)
    assert names_after_up2 == names_after_up


def test_indexes_present(alembic_db) -> None:
    """Spot-check the indexes we actually use for query performance."""
    cfg, db_path = alembic_db
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migrations"))
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(db_path)) as conn:
        assert "ix_series_followed" in _indexes(conn, "series")
        assert "ix_series_library_id" in _indexes(conn, "series")
        assert "ix_chapters_volume_sort" in _indexes(conn, "chapters")
        assert "ix_chapters_language" in _indexes(conn, "chapters")
        assert "ix_libraries_type" in _indexes(conn, "libraries")
        assert "ix_jobs_status_started" in _indexes(conn, "provider_jobs")
        assert "ix_domain_health_source_healthy" in _indexes(conn, "domain_health")
