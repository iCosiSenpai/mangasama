"""API tests for `/api/libraries`."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import session_scope
from app.main import create_app
from app.models.orm import Chapter, Series, Volume
from app.settings import get_settings


@pytest.fixture
async def client():
    """Yield an httpx ASGI client wired to a fresh app instance.

    Schema is initialised by the autouse `_http_client` fixture.
    """
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as ac:
        yield ac


# --------------------------------------------------------- happy path


@pytest.mark.asyncio
async def test_create_list_get_library(client: AsyncClient, tmp_path: Path) -> None:
    payload = {
        "name": "Manga IT",
        "type": "manga",
        "root_path": str(tmp_path / "manga_it"),
        "providers": ["mangaworld", "mangadex"],
    }
    r = await client.post("/api/libraries", json=payload)
    assert r.status_code == 201, r.text
    lib = r.json()
    assert lib["name"] == "Manga IT"
    assert lib["type"] == "manga"
    assert lib["series_count"] == 0
    lib_id = lib["id"]

    r = await client.get("/api/libraries")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["id"] == lib_id

    r = await client.get(f"/api/libraries/{lib_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "Manga IT"


# ---------------------------------------------------------- 400 errors


@pytest.mark.asyncio
async def test_create_library_invalid_type(client: AsyncClient, tmp_path: Path) -> None:
    payload = {
        "name": "Bad",
        "type": "novel",  # not in {manga, manhua, manhwa}
        "root_path": str(tmp_path / "bad"),
    }
    r = await client.post("/api/libraries", json=payload)
    assert r.status_code == 400
    assert r.json()["type"] == "validation_error"


@pytest.mark.asyncio
async def test_create_library_unknown_folder_strategy(
    client: AsyncClient, tmp_path: Path,
) -> None:
    payload = {
        "name": "Weird",
        "type": "manga",
        "root_path": str(tmp_path / "weird"),
        "folder_strategy": "weird_value",
    }
    r = await client.post("/api/libraries", json=payload)
    assert r.status_code == 400
    assert r.json()["type"] == "validation_error"


@pytest.mark.asyncio
async def test_create_library_duplicate_name(
    client: AsyncClient, tmp_path: Path,
) -> None:
    payload = {
        "name": "Dup",
        "type": "manga",
        "root_path": str(tmp_path / "dup"),
    }
    r1 = await client.post("/api/libraries", json=payload)
    assert r1.status_code == 201
    r2 = await client.post("/api/libraries", json=payload)
    assert r2.status_code == 400
    assert r2.json()["type"] == "invalid_value"


# ------------------------------------------------------------------ 404


@pytest.mark.asyncio
async def test_get_library_not_found(client: AsyncClient) -> None:
    r = await client.get("/api/libraries/9999")
    assert r.status_code == 404
    assert r.json()["type"] == "library_not_found"


# ----------------------------------------------------------------- soft delete


@pytest.mark.asyncio
async def test_soft_delete_library(client: AsyncClient, tmp_path: Path) -> None:
    payload = {
        "name": "Trash",
        "type": "manga",
        "root_path": str(tmp_path / "trash"),
    }
    lib = (await client.post("/api/libraries", json=payload)).json()
    lib_id = lib["id"]

    r = await client.delete(f"/api/libraries/{lib_id}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    # Subsequent GET hides the deleted library.
    r = await client.get(f"/api/libraries/{lib_id}")
    assert r.status_code == 404

    # The list endpoint also filters it out by default.
    r = await client.get("/api/libraries")
    assert all(row["id"] != lib_id for row in r.json())


# ------------------------------------------------------------------- patch


@pytest.mark.asyncio
async def test_patch_library(
    client: AsyncClient, tmp_path: Path,
) -> None:
    payload = {
        "name": "Old",
        "type": "manga",
        "root_path": str(tmp_path / "old"),
        "jpg_quality": 80,
    }
    lib = (await client.post("/api/libraries", json=payload)).json()
    lib_id = lib["id"]

    r = await client.patch(
        f"/api/libraries/{lib_id}",
        json={"jpg_quality": 90, "follow_interval_hours": 12},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["jpg_quality"] == 90
    assert body["follow_interval_hours"] == 12
    assert body["name"] == "Old"  # untouched


# ------------------------------------------------------------------- stats


@pytest.mark.asyncio
async def test_library_stats_empty(
    client: AsyncClient, tmp_path: Path,
) -> None:
    payload = {
        "name": "Empty",
        "type": "manga",
        "root_path": str(tmp_path / "empty"),
    }
    lib = (await client.post("/api/libraries", json=payload)).json()
    r = await client.get(f"/api/libraries/{lib['id']}/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["series_count"] == 0
    assert body["chapter_count"] == 0
    assert body["downloaded_chapter_count"] == 0
    assert body["total_cbz_bytes"] == 0


@pytest.mark.asyncio
async def test_library_stats_with_chapters(
    client: AsyncClient, tmp_path: Path,
) -> None:
    lib = (await client.post("/api/libraries", json={
        "name": "Stats", "type": "manga", "root_path": str(tmp_path / "stats"),
    })).json()
    lib_id = lib["id"]

    # One series, one volume, two chapters (one downloaded with a CBZ size).
    async with session_scope() as s:
        series = Series(library_id=lib_id, title="S", sort_title="S")
        s.add(series)
        await s.flush()
        vol = Volume(series_id=series.id, number="1", sort=1.0, language="it")
        s.add(vol)
        await s.flush()
        s.add(Chapter(
            volume_id=vol.id, number="1", sort=1.0, language="it",
            source_provider="mangadex", source_id="a",
            file_path="/data/a.cbz", cbz_size=1000,
            downloaded_at=datetime.now(timezone.utc),
        ))
        s.add(Chapter(
            volume_id=vol.id, number="2", sort=2.0, language="it",
            source_provider="mangadex", source_id="b",
        ))

    r = await client.get(f"/api/libraries/{lib_id}/stats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["series_count"] == 1
    assert body["chapter_count"] == 2
    assert body["downloaded_chapter_count"] == 1
    assert body["total_cbz_bytes"] == 1000
