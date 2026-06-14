"""Smoke test: settings + DB init + health endpoint shape."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint():
    """Step 1 checkpoint: the API boots and /api/health returns 200."""
    from app.main import create_app
    from app.settings import get_settings

    get_settings.cache_clear()
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/health")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "ok"
        assert data["app"] == "MangaSama"
        assert "version" in data
        assert "uptime_seconds" in data


@pytest.mark.asyncio
async def test_db_init_creates_tables():
    """Step 1 checkpoint: init_db() creates all 12 expected tables."""
    from app.db.init import init_db
    from app.settings import get_settings

    get_settings.cache_clear()
    await init_db()

    # Inspect the file.
    settings = get_settings()
    import sqlite3

    db_path = settings.data_dir / settings.db_filename
    assert db_path.exists(), f"DB file not found at {db_path}"
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        names = {r[0] for r in rows}
    expected = {
        "libraries", "series", "series_external_ids", "series_genres",
        "series_tags", "series_authors", "volumes", "chapters", "pages",
        "follow_log", "provider_jobs", "domain_health",
    }
    missing = expected - names
    assert not missing, f"Missing tables: {missing}"
