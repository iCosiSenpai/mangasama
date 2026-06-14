"""API tests for `/api/jobs` (list, get, SSE stream)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import session_scope
from app.main import create_app
from app.models.orm import ProviderJob
from app.services import job_events
from app.settings import get_settings


@pytest.fixture
async def client():
    get_settings.cache_clear()
    job_events.reset_for_tests()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as ac:
        yield ac
    job_events.reset_for_tests()


async def _seed_jobs() -> None:
    now = datetime.now(timezone.utc)
    async with session_scope() as s:
        s.add(ProviderJob(job_type="download", provider="mangadex", status="done",
                          progress=100, finished_at=now))
        s.add(ProviderJob(job_type="download", provider="mangadex", status="error",
                          error="boom", finished_at=now))
        s.add(ProviderJob(job_type="metadata_enrich", provider="anilist", status="running"))


@pytest.mark.asyncio
async def test_list_jobs_and_filters(client: AsyncClient) -> None:
    await _seed_jobs()

    r = await client.get("/api/jobs")
    assert r.status_code == 200
    assert len(r.json()) == 3
    # Newest first.
    assert r.json()[0]["id"] > r.json()[-1]["id"]

    r = await client.get("/api/jobs?status=done")
    assert [j["status"] for j in r.json()] == ["done"]

    r = await client.get("/api/jobs?job_type=metadata_enrich")
    assert [j["job_type"] for j in r.json()] == ["metadata_enrich"]


@pytest.mark.asyncio
async def test_get_job_and_404(client: AsyncClient) -> None:
    await _seed_jobs()
    r = await client.get("/api/jobs?limit=1")
    jid = r.json()[0]["id"]

    r = await client.get(f"/api/jobs/{jid}")
    assert r.status_code == 200
    assert r.json()["id"] == jid

    r = await client.get("/api/jobs/999999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_job_event_stream_generator() -> None:
    """Drive the SSE body generator directly (no HTTP stream, deterministic)."""
    from app.api.jobs import job_event_stream

    agen = job_event_stream(keepalive=0.2)
    try:
        first = await asyncio.wait_for(agen.__anext__(), timeout=2)
        assert "connected" in first
        # A published event is forwarded as a `data:` frame.
        job_events.publish_job({"id": 999, "status": "running"})
        frame = await asyncio.wait_for(agen.__anext__(), timeout=2)
        assert frame.startswith("data:") and "999" in frame
        # With no events, the generator emits a keepalive after the timeout.
        ka = await asyncio.wait_for(agen.__anext__(), timeout=2)
        assert "keepalive" in ka
    finally:
        await agen.aclose()
