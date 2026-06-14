"""Pytest configuration — load env + ensure asyncio mode."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Make `app.*` importable from tests/ without install.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _env():
    """Use a per-test temp data dir so DB state doesn't leak between tests.

    Each test gets its own `DATA_DIR` under a fresh `mkdtemp` so the
    `Settings.db_url` is unique. The async engine is built lazily
    from this URL and disposed by the `_http_client` fixture below.
    """
    tmp = Path(tempfile.mkdtemp(prefix="mangasama-test-"))
    os.environ["DATA_DIR"] = str(tmp / "data")
    os.environ["CONFIG_DIR"] = str(tmp / "config")
    os.environ["AUTH_ENABLED"] = "false"
    os.environ["CLOUDFLARE_SOLVER"] = ""
    # Invalidate the lru_cache on Settings so the new DATA_DIR takes effect.
    from app.settings import get_settings
    get_settings.cache_clear()
    # Force a fresh async engine against the new URL.
    from app.db import base as db_base
    db_base._engine = None
    db_base._sessionmaker = None
    yield


@pytest.fixture(autouse=True)
async def _http_client():
    """Start the shared HTTP client per test, init the schema, and reset
    the rate limiter. Also disposes the async engine after the test so
    the next test gets a clean one.
    """
    from app.core.http_client import get_http
    from app.core.rate_limiter import reset_for_tests as reset_rl
    from app.db import base as db_base
    from app.db.base import dispose_engine
    from app.db.init import init_db
    from app.scrapers.registry import reset_for_tests as reset_registry

    reset_rl()
    reset_registry()
    http = get_http()
    await http.start()
    # Initialise the schema (create_all) so any test can write to the DB.
    await init_db()
    try:
        yield
    finally:
        await http.close()
        try:
            await dispose_engine()
        except Exception:
            pass
        db_base._engine = None
        db_base._sessionmaker = None
