"""Tests for the domain-exception → HTTP JSON mapping."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import (
    DownloadQueueFull,
    JobNotFound,
    UnknownScraper,
)
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
async def test_job_not_found_envelope(client: AsyncClient) -> None:
    r = await client.get("/api/jobs/999999")
    assert r.status_code == 404
    body = r.json()
    assert body["type"] == "job_not_found"
    assert "detail" in body


@pytest.mark.asyncio
async def test_cover_not_found_envelope(client: AsyncClient) -> None:
    r = await client.get("/api/covers/series/999999")
    assert r.status_code == 404
    # Series itself is missing → series_not_found (raised before the cover check).
    assert r.json()["type"] in {"series_not_found", "cover_not_found"}


@pytest.mark.asyncio
async def test_unknown_scraper_maps_to_400(client: AsyncClient) -> None:
    # A library with a bogus provider, then add a series via that provider.
    lib = await client.post(
        "/api/libraries",
        json={
            "name": "L",
            "type": "manga",
            "root_path": "/tmp/l",
            "folder_strategy": "series_volume_chapter",
            "providers": ["mangadex"],
            "italian_priority": True,
            "follow_interval_hours": 24,
            "jpg_quality": 85,
        },
    )
    assert lib.status_code == 201, lib.text
    r = await client.post(
        "/api/series",
        json={
            "library_id": lib.json()["id"],
            "provider": "does_not_exist",
            "external_id": "x",
        },
    )
    assert r.status_code == 400
    assert r.json()["type"] == "config_error"


@pytest.mark.asyncio
async def test_generic_exception_returns_clean_500(monkeypatch) -> None:
    from app.services import library as library_service

    async def boom(*args, **kwargs):
        raise RuntimeError("kaboom secret internals")

    monkeypatch.setattr(library_service, "list_libraries", boom)
    get_settings.cache_clear()
    app = create_app()
    # Starlette's ServerErrorMiddleware re-raises after sending the response so
    # the ASGI server can log it; disable re-raise here to inspect the response
    # the real client would receive.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/libraries")
    get_settings.cache_clear()
    assert r.status_code == 500
    body = r.json()
    assert body["type"] == "internal_error"
    # The real cause must not leak to the client.
    assert "kaboom" not in body["detail"]


def test_unknown_scraper_is_keyerror_compatible() -> None:
    # Existing `except KeyError` call sites must keep catching it.
    assert issubclass(UnknownScraper, KeyError)


@pytest.mark.asyncio
async def test_download_queue_full_raises_domain_error() -> None:
    from app.scrapers.base import ScrapedChapter
    from app.services.downloader import DownloadQueue, DownloadTask

    q = DownloadQueue()
    q._queue = asyncio.Queue(maxsize=1)
    task = DownloadTask(
        series_id=1,
        provider="mangadex",
        chapter=ScrapedChapter(
            source="mangadex", external_id="a", url="https://x/a", number="1", language="it",
        ),
        language="it",
    )
    q.enqueue(task)  # fills the queue
    with pytest.raises(DownloadQueueFull):
        q.enqueue(task)


def test_job_not_found_is_mangasama_error() -> None:
    from app.core.exceptions import MangaSamaError

    assert issubclass(JobNotFound, MangaSamaError)
