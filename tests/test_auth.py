"""Tests for the optional HTTP Basic auth gate."""

from __future__ import annotations

import base64

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.settings import get_settings


def _basic(user: str, pw: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


@pytest.fixture
async def auth_client(monkeypatch):
    """An app instance with AUTH_ENABLED=true and a known admin password."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    get_settings.cache_clear()
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
    r = await auth_client.get("/api/libraries", headers={"Authorization": _basic("admin", "secret")})
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
async def test_opds_requires_auth(auth_client: AsyncClient) -> None:
    r = await auth_client.get("/opds/v1.2/root")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_auth_disabled_allows_all() -> None:
    # Default env (conftest sets AUTH_ENABLED=false): no gate.
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/libraries")
    assert r.status_code == 200


@pytest.fixture
async def lockout_client(monkeypatch):
    """Auth enabled with a low failure threshold to exercise the lockout."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("AUTH_MAX_FAILURES", "3")
    monkeypatch.setenv("AUTH_LOCKOUT_SECONDS", "60")
    get_settings.cache_clear()
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
        "/api/libraries", headers={"Authorization": _basic("admin", "secret")}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_non_basic_scheme_does_not_count_toward_lockout(
    lockout_client: AsyncClient,
) -> None:
    # Bearer (or any non-Basic) scheme must not accrue Basic-auth failures.
    for _ in range(5):
        r = await lockout_client.get(
            "/api/libraries", headers={"Authorization": "Bearer sometoken"}
        )
        assert r.status_code == 401
    # No lockout → correct Basic credentials still work.
    r = await lockout_client.get(
        "/api/libraries", headers={"Authorization": _basic("admin", "secret")}
    )
    assert r.status_code == 200
