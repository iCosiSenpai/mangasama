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
