"""Tests for the HTTP Basic auth gate (active after first-run setup)."""

from __future__ import annotations

import base64

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import setup_state
from app.main import create_app
from app.settings import get_settings


def _basic(user: str, pw: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


TEST_PASSWORD = "verysecret"


def _write_test_admin(config_dir: str, username: str = "admin", password: str = TEST_PASSWORD) -> None:
    setup_state.write_admin(username, password)


@pytest.fixture
async def auth_client(monkeypatch, tmp_path):
    """An app instance with a completed setup and a known admin password."""
    config_dir = tmp_path / "config"
    monkeypatch.setenv("CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    # Create the admin account file before booting the app.
    _write_test_admin(str(config_dir), "admin", TEST_PASSWORD)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_api_requires_auth(auth_client: AsyncClient) -> None:
    r = await auth_client.get("/api/libraries")
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate", "").lower().startswith("basic")


@pytest.mark.asyncio
async def test_api_with_correct_password(auth_client: AsyncClient) -> None:
    r = await auth_client.get("/api/libraries", headers={"Authorization": _basic("admin", TEST_PASSWORD)})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_api_with_wrong_password(auth_client: AsyncClient) -> None:
    r = await auth_client.get("/api/libraries", headers={"Authorization": _basic("admin", "nope")})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_health_is_public(auth_client: AsyncClient) -> None:
    r = await auth_client.get("/api/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_setup_is_public(auth_client: AsyncClient) -> None:
    # /api/setup/status stays public even after setup, and /api/setup is
    # unavailable once completed.
    r = await auth_client.get("/api/setup/status")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_opds_requires_auth(auth_client: AsyncClient) -> None:
    r = await auth_client.get("/opds/v1.2/root")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_no_setup_allows_all(monkeypatch, tmp_path) -> None:
    # Default env with no admin.json: no gate, public API.
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/libraries")
    assert r.status_code == 200
    get_settings.cache_clear()


@pytest.fixture
async def lockout_client(monkeypatch, tmp_path):
    """Setup completed with a low failure threshold to exercise the lockout."""
    config_dir = tmp_path / "config"
    monkeypatch.setenv("CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AUTH_MAX_FAILURES", "3")
    monkeypatch.setenv("AUTH_LOCKOUT_SECONDS", "60")
    get_settings.cache_clear()
    _write_test_admin(str(config_dir), "admin", TEST_PASSWORD)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_repeated_wrong_passwords_trigger_lockout(lockout_client: AsyncClient) -> None:
    wrong = {"Authorization": _basic("admin", "nope")}
    # First 3 wrong attempts → 401.
    for _ in range(3):
        r = await lockout_client.get("/api/libraries", headers=wrong)
        assert r.status_code == 401
    # 4th attempt is locked out → 429 with Retry-After.
    r = await lockout_client.get("/api/libraries", headers=wrong)
    assert r.status_code == 429
    assert r.headers.get("Retry-After") == "60"


@pytest.mark.asyncio
async def test_headerless_requests_do_not_count_toward_lockout(
    lockout_client: AsyncClient,
) -> None:
    # A browser's first (credential-less) request must not trip the lock.
    for _ in range(5):
        r = await lockout_client.get("/api/libraries")
        assert r.status_code == 401
    # A correct password still works (no lockout accrued).
    r = await lockout_client.get(
        "/api/libraries", headers={"Authorization": _basic("admin", TEST_PASSWORD)}
    )
    assert r.status_code == 200
