"""API tests for `/api/chapters`."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert

from app.db.session import session_scope
from app.main import create_app
from app.models.orm import Chapter, Library, Series, Volume
from app.settings import get_settings


@pytest.fixture
async def client():
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as ac:
        yield ac


async def _seed_chapters(
    languages: list[str], *, with_files: list[bool] | None = None,
) -> tuple[int, int]:
    """Insert a library + series + volume with one chapter per language.

    Returns `(series_id, [chapter_ids...])`. The `with_files` mask
    mirrors `languages` length; `True` means `file_path` is set, else
    `None`. Defaults to all-None.
    """
    with_files = with_files or [False] * len(languages)
    assert len(with_files) == len(languages)
    async with session_scope() as s:
        lib = Library(
            name="TestLib", type="manga", root_path="/tmp/test_chapters",
            folder_strategy="series_volume_chapter", providers=["mangadex"],
        )
        s.add(lib)
        await s.flush()
        series = Series(
            library_id=lib.id, title="Test Series", sort_title="Test Series",
        )
        s.add(series)
        await s.flush()
        vol = Volume(series_id=series.id, number="1", sort=1.0)
        s.add(vol)
        await s.flush()
        ids = []
        for i, (lang, has_file) in enumerate(zip(languages, with_files)):
            ch = Chapter(
                volume_id=vol.id, number=str(i + 1), sort=float(i + 1),
                title=f"Chapter {i + 1}",
                source_provider="mangadex",
                source_id=f"src-{i}",
                language=lang,
                file_path=("/tmp/test_chapters/x.cbz" if has_file else None),
            )
            s.add(ch)
            await s.flush()
            ids.append(ch.id)
    return series.id, ids


# ----------------------------------------------------------------- ordering


@pytest.mark.asyncio
async def test_list_chapters_italian_first(client: AsyncClient) -> None:
    # Insert in non-Italian-first order on purpose: en, it, ja.
    _, ids = await _seed_chapters(["en", "it", "ja"])
    r = await client.get("/api/chapters")
    assert r.status_code == 200
    rows = r.json()
    # Filter to our 3 chapters.
    rows = [r for r in rows if r["id"] in ids]
    assert len(rows) == 3
    # Italian first, then English, then Japanese.
    assert rows[0]["language"] == "it"
    assert rows[1]["language"] == "en"
    assert rows[2]["language"] == "ja"


# -------------------------------------------------------------- 404 cases


@pytest.mark.asyncio
async def test_chapter_file_404_when_no_file(client: AsyncClient) -> None:
    _, ids = await _seed_chapters(["it"])  # no file
    r = await client.get(f"/api/chapters/{ids[0]}/file")
    assert r.status_code == 404
    assert r.json()["type"] == "chapter_not_found"


@pytest.mark.asyncio
async def test_chapter_get_not_found(client: AsyncClient) -> None:
    r = await client.get("/api/chapters/9999")
    assert r.status_code == 404
    assert r.json()["type"] == "chapter_not_found"


# ------------------------------------------------------------------ delete


@pytest.mark.asyncio
async def test_delete_chapter(client: AsyncClient) -> None:
    _, ids = await _seed_chapters(["it"])
    r = await client.delete(f"/api/chapters/{ids[0]}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    r = await client.get(f"/api/chapters/{ids[0]}")
    assert r.status_code == 404
