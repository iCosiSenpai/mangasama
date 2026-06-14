"""Tests for the download engine (`app/services/downloader.py`)."""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.session import session_scope
from app.models.orm import (
    Chapter,
    Library,
    Page,
    Series,
    SeriesAuthor,
    SeriesGenre,
    SeriesTag,
    Volume,
)
from app.scrapers.base import BaseScraper, ScrapedChapter, ScrapedPage
from app.services import downloader


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, "PNG")
    return buf.getvalue()


class FakeScraper(BaseScraper):
    name = "testsrc"
    display_name = "Test Source"
    base_url = "https://cdn.test"
    rate_limit_rpm = 1000

    def __init__(self, pages: list[ScrapedPage]):
        super().__init__(http=object())
        self._pages = pages
        self.get_pages_calls = 0

    async def health_check(self) -> bool:
        return True

    async def search(self, query, *, limit=20, language=None):
        return []

    async def get_series(self, url_or_id):
        raise NotImplementedError

    async def get_chapters(self, external_id, *, language=None, limit=500, offset=0):
        return []

    async def get_pages(self, chapter_external_id):
        self.get_pages_calls += 1
        return list(self._pages)


class FakeHttp:
    def __init__(self, data: bytes):
        self.data = data
        self.calls = 0

    async def get_bytes(self, url, *, scraper, domain, rpm=None):
        self.calls += 1
        return self.data


@pytest.fixture(autouse=True)
def _reset_queue():
    downloader.reset_for_tests()
    yield
    downloader.reset_for_tests()


async def _make_series(root: Path) -> tuple[int, int]:
    async with session_scope() as s:
        lib = Library(
            name="DLTest", type="manga", root_path=str(root),
            folder_strategy="series_volume_chapter", providers=["testsrc"],
        )
        s.add(lib)
        await s.flush()
        series = Series(
            library_id=lib.id, title="Berserk", sort_title="Berserk",
            language="it", summary="A dark fantasy.",
        )
        s.add(series)
        await s.flush()
        s.add(SeriesAuthor(series_id=series.id, role="writer", name="Kentaro Miura"))
        s.add(SeriesGenre(series_id=series.id, genre="Action"))
        s.add(SeriesTag(series_id=series.id, tag="Dark Fantasy"))
        return lib.id, series.id


async def _load_for_download(session, series_id: int) -> Series:
    return (
        await session.execute(
            select(Series).where(Series.id == series_id).options(
                selectinload(Series.authors),
                selectinload(Series.genres),
                selectinload(Series.tags),
                selectinload(Series.library),
            )
        )
    ).scalar_one()


def _scraped(num: str = "1") -> ScrapedChapter:
    return ScrapedChapter(
        source="testsrc", external_id=f"c{num}", url=f"https://x/c{num}",
        number=num, title="Start", language="it", volume_number="1",
    )


@pytest.mark.asyncio
async def test_download_chapter_writes_cbz_and_rows(tmp_path, monkeypatch):
    fake_http = FakeHttp(_png_bytes())
    monkeypatch.setattr(downloader, "get_http", lambda: fake_http)
    scraper = FakeScraper([
        ScrapedPage(index=0, url="https://cdn.test/0.png"),
        ScrapedPage(index=1, url="https://cdn.test/1.png"),
    ])
    _, series_id = await _make_series(tmp_path / "lib")

    async with session_scope() as session:
        series = await _load_for_download(session, series_id)
        ch = await downloader.download_chapter(
            session, series=series, scraped=_scraped("1"),
            scraper=scraper, library=series.library,
        )
        assert ch is not None
        cbz_path = Path(ch.file_path)

    # CBZ exists and contains ComicInfo + zero-padded pages.
    assert cbz_path.exists()
    with zipfile.ZipFile(cbz_path) as zf:
        names = zf.namelist()
    assert names == ["ComicInfo.xml", "page001.jpg", "page002.jpg"]
    assert scraper.get_pages_calls == 1
    assert fake_http.calls == 2

    # Chapter + Page rows persisted.
    async with session_scope() as session:
        chapters = (await session.execute(select(Chapter))).scalars().all()
        assert len(chapters) == 1
        assert chapters[0].pages_count == 2
        assert chapters[0].cbz_sha256
        page_count = (await session.execute(select(func.count(Page.id)))).scalar_one()
        assert page_count == 2
        vol_count = (await session.execute(select(func.count(Volume.id)))).scalar_one()
        assert vol_count == 1


@pytest.mark.asyncio
async def test_download_chapter_is_idempotent(tmp_path, monkeypatch):
    fake_http = FakeHttp(_png_bytes())
    monkeypatch.setattr(downloader, "get_http", lambda: fake_http)
    scraper = FakeScraper([ScrapedPage(index=0, url="https://cdn.test/0.png")])
    _, series_id = await _make_series(tmp_path / "lib")

    async with session_scope() as session:
        series = await _load_for_download(session, series_id)
        first = await downloader.download_chapter(
            session, series=series, scraped=_scraped("1"),
            scraper=scraper, library=series.library,
        )
        first_id, first_sha = first.id, first.cbz_sha256

    # Second call: same chapter, file present → skip (no re-fetch).
    async with session_scope() as session:
        series = await _load_for_download(session, series_id)
        second = await downloader.download_chapter(
            session, series=series, scraped=_scraped("1"),
            scraper=scraper, library=series.library,
        )
        assert second.id == first_id

    assert scraper.get_pages_calls == 1  # not called again
    async with session_scope() as session:
        chapters = (await session.execute(select(Chapter))).scalars().all()
        assert len(chapters) == 1

    # overwrite=True re-fetches and rebuilds with the same deterministic sha.
    async with session_scope() as session:
        series = await _load_for_download(session, series_id)
        third = await downloader.download_chapter(
            session, series=series, scraped=_scraped("1"),
            scraper=scraper, library=series.library, overwrite=True,
        )
        assert third.cbz_sha256 == first_sha
    assert scraper.get_pages_calls == 2


@pytest.mark.asyncio
async def test_download_chapter_no_pages_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader, "get_http", lambda: FakeHttp(_png_bytes()))
    scraper = FakeScraper([])  # source yields no pages
    _, series_id = await _make_series(tmp_path / "lib")

    async with session_scope() as session:
        series = await _load_for_download(session, series_id)
        ch = await downloader.download_chapter(
            session, series=series, scraped=_scraped("1"),
            scraper=scraper, library=series.library,
        )
        assert ch is None
        assert (await session.execute(select(func.count(Chapter.id)))).scalar_one() == 0
