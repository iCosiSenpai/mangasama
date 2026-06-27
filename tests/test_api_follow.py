"""API tests for `/api/follow` (list + manual check)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import session_scope
from app.main import create_app
from app.models.orm import FollowLog, Library, Series, SeriesExternalId
from app.scrapers.base import ScrapedChapter
from app.services import follow as follow_service
from app.settings import get_settings


@pytest.fixture
async def client():
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as ac:
        yield ac


async def _make_followed_series(*, with_log: bool = False) -> int:
    async with session_scope() as s:
        lib = Library(
            name="FollowApi", type="manga", root_path="/tmp/fa",
            folder_strategy="series_volume_chapter", providers=["mangadex"],
            italian_priority=True,
        )
        s.add(lib)
        await s.flush()
        series = Series(
            library_id=lib.id, title="Berserk", sort_title="Berserk",
            language="it", followed=True,
        )
        s.add(series)
        await s.flush()
        s.add(SeriesExternalId(series_id=series.id, provider="mangadex", external_id="md1"))
        if with_log:
            s.add(FollowLog(series_id=series.id, new_chapters_count=3, status="ok"))
        return series.id


@pytest.mark.asyncio
async def test_list_follows(client: AsyncClient) -> None:
    sid = await _make_followed_series(with_log=True)
    r = await client.get("/api/follow")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    row = body[0]
    assert row["series_id"] == sid
    assert row["title"] == "Berserk"
    assert row["last_status"] == "ok"
    assert row["last_new_chapters"] == 3


@pytest.mark.asyncio
async def test_check_follow_enqueues(client: AsyncClient, monkeypatch) -> None:
    collected: list = []
    monkeypatch.setattr(follow_service, "enqueue_download", lambda t: collected.append(t))

    from app.scrapers import mangadex as md_module

    async def fake_chapters(self, external_id, *, language=None, limit=500, offset=0):
        return [
            ScrapedChapter(source="mangadex", external_id=f"c{i}", url="",
                           number=str(i), language="it", volume_number="1")
            for i in (1, 2)
        ]

    monkeypatch.setattr(md_module.MangaDexScraper, "get_chapters", fake_chapters)
    sid = await _make_followed_series()

    r = await client.post(f"/api/follow/{sid}/check")
    assert r.status_code == 200, r.text
    assert r.json()["enqueued"] == 2
    assert r.json()["status"] == "ok"
    assert len(collected) == 2

    # A FollowLog row was persisted.
    from sqlalchemy import func, select
    async with session_scope() as s:
        n = (await s.execute(select(func.count(FollowLog.id)))).scalar_one()
    assert n == 1


@pytest.mark.asyncio
async def test_check_follow_queue_full_returns_503(client: AsyncClient, monkeypatch) -> None:
    from app.core.exceptions import DownloadQueueFull
    from app.scrapers import mangadex as md_module

    def boom(_task):
        raise DownloadQueueFull("queue is full")

    monkeypatch.setattr(follow_service, "enqueue_download", boom)

    async def fake_chapters(self, external_id, *, language=None, limit=500, offset=0):
        return [ScrapedChapter(source="mangadex", external_id="c1", url="",
                               number="1", language="it", volume_number="1")]

    monkeypatch.setattr(md_module.MangaDexScraper, "get_chapters", fake_chapters)
    sid = await _make_followed_series()

    r = await client.post(f"/api/follow/{sid}/check")
    assert r.status_code == 503
    assert r.json()["type"] == "download_queue_full"
