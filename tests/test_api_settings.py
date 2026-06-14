"""API tests for `/api/settings`."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import session_scope
from app.main import create_app
from app.models.orm import DomainHealth
from app.settings import get_settings


@pytest.fixture
async def client():
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_settings(client: AsyncClient) -> None:
    r = await client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert "library_defaults" in body
    assert "known_scrapers" in body
    assert "mangadex" in body["known_scrapers"]


@pytest.mark.asyncio
async def test_patch_settings_log_level(client: AsyncClient) -> None:
    r = await client.patch("/api/settings", json={"log_level": "DEBUG"})
    assert r.status_code == 200
    assert r.json()["log_level"] == "DEBUG"


@pytest.mark.asyncio
async def test_patch_settings_unknown_field(client: AsyncClient) -> None:
    r = await client.patch("/api/settings", json={"foo": "bar"})
    assert r.status_code == 400
    # Pydantic v2 `extra="forbid"` triggers a RequestValidationError,
    # which our handler maps to 400 + `type=validation_error`.
    assert r.json()["type"] == "validation_error"


@pytest.mark.asyncio
async def test_provider_health_empty(client: AsyncClient) -> None:
    r = await client.get("/api/settings/providers/health")
    assert r.status_code == 200
    body = r.json()
    assert "providers" in body
    # All known scrapers should appear (healthy=True by default).
    names = [p["provider"] for p in body["providers"]]
    assert "mangadex" in names


@pytest.mark.asyncio
async def test_reset_provider_health(client: AsyncClient) -> None:
    # Seed an unhealthy mangadex domain, then reset it via the admin endpoint.
    async with session_scope() as s:
        s.add(DomainHealth(
            source="mangadex", domain="api.mangadex.org",
            healthy=False, fail_count=5,
        ))

    r = await client.post("/api/settings/providers/mangadex/reset")
    assert r.status_code == 200, r.text
    md = next(p for p in r.json()["providers"] if p["provider"] == "mangadex")
    assert md["healthy"] is True
    assert md["fail_count"] == 0


@pytest.mark.asyncio
async def test_run_provider_health_check(client: AsyncClient, monkeypatch) -> None:
    import httpx

    from app.services import health

    class FakeClient:
        async def get(self, url):
            return httpx.Response(200, request=httpx.Request("GET", url))

        async def aclose(self):
            pass

    monkeypatch.setattr(health, "make_health_client", lambda: FakeClient())
    r = await client.post("/api/settings/providers/health/check")
    assert r.status_code == 200
    names = [p["provider"] for p in r.json()["providers"]]
    assert "mangadex" in names


@pytest.mark.asyncio
async def test_run_backup(client: AsyncClient) -> None:
    r = await client.post("/api/settings/backup")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"].startswith("mangasama-")
    assert body["total_backups"] >= 1
    assert (get_settings().backups_dir / body["created"]).exists()
