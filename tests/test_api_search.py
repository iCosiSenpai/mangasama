"""API tests for `POST /api/search`."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.scrapers.base import ScrapedSeries
from app.settings import get_settings


@pytest.fixture
async def client():
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as ac:
        yield ac


async def _make_library(name: str, providers: list[str]) -> int:
    from app.db.session import session_scope
    from app.models.orm import Library

    async with session_scope() as s:
        lib = Library(
            name=name, type="manga", root_path=f"/tmp/{name}",
            folder_strategy="series_volume_chapter", providers=providers,
        )
        s.add(lib)
        await s.flush()
        return lib.id


def _scraped(external_id: str, title: str) -> ScrapedSeries:
    return ScrapedSeries(
        source="mangadex", external_id=external_id, url="",
        title=title, alt_titles=[], summary=None, year=None,
        status=None, cover_url=None, authors=[], genres=[], tags=[],
        type="manga",
    )


@pytest.mark.asyncio
@respx.mock
async def test_multi_source_search_merges_results(client: AsyncClient) -> None:
    lib_id = await _make_library("Multi", ["mangadex", "mangaworld"])
    respx.get("https://api.mangadex.org/manga").mock(
        return_value=httpx.Response(200, json={
            "result": "ok",
            "data": [
                {
                    "id": "md-1", "attributes": {
                        "title": {"en": "Naruto"},
                        "altTitles": [], "year": 1999,
                    },
                    "relationships": [],
                },
            ],
        }),
    )
    respx.get(url__regex=r"https://www\.mangaworld\.mx/archive.*").mock(
        return_value=httpx.Response(200, text="<html><body></body></html>"),
    )

    r = await client.post("/api/search", json={
        "library_id": lib_id, "query": "naruto",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    # The MangaDex mock yields one result; mangaworld's archive
    # endpoint may also return at least 0 — we only assert the
    # positive case.
    titles = [c["title"] for c in body["candidates"]]
    assert "Naruto" in titles
    assert "mangadex" in body["providers_used"]


@pytest.mark.asyncio
@respx.mock
async def test_search_provider_offline_doesnt_500(client: AsyncClient) -> None:
    lib_id = await _make_library("Offline", ["mangadex"])
    respx.get("https://api.mangadex.org/manga").mock(
        return_value=httpx.Response(500, json={"result": "error"}),
    )
    r = await client.post("/api/search", json={
        "library_id": lib_id, "query": "anything",
    })
    assert r.status_code == 200
    # The orchestrator degrades gracefully: zero candidates.
    assert r.json()["candidates"] == []


@pytest.mark.asyncio
async def test_search_unknown_library(client: AsyncClient) -> None:
    r = await client.post("/api/search", json={
        "library_id": 9999, "query": "x",
    })
    assert r.status_code == 404
    assert r.json()["type"] == "library_not_found"
