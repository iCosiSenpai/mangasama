"""Tests for the security-headers middleware."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.settings import get_settings


@pytest.fixture
async def client():
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_baseline_security_headers_present(client: AsyncClient) -> None:
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "Permissions-Policy" in r.headers


@pytest.mark.asyncio
async def test_csp_present_on_api(client: AsyncClient) -> None:
    r = await client.get("/api/health")
    csp = r.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


@pytest.mark.asyncio
async def test_csp_skipped_for_docs(client: AsyncClient) -> None:
    # Swagger UI needs CDN assets + inline scripts; a strict CSP would break it.
    r = await client.get("/api/docs")
    assert r.status_code == 200
    assert "Content-Security-Policy" not in r.headers
    # Baseline headers still apply.
    assert r.headers["X-Content-Type-Options"] == "nosniff"
