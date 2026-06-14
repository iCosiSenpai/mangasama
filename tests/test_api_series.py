"""API tests for `/api/series`."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import session_scope
from app.main import create_app
from app.models.orm import Library, Series
from app.scrapers.base import ScrapedChapter, ScrapedSeries
from app.settings import get_settings


@pytest.fixture
async def client():
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as ac:
        yield ac


async def _make_library(name: str = "SeriesTest") -> int:
    async with session_scope() as s:
        lib = Library(
            name=name, type="manga", root_path=f"/tmp/{name}",
            folder_strategy="series_volume_chapter", providers=["mangadex"],
        )
        s.add(lib)
        await s.flush()
        return lib.id


def _fake_scraped(external_id: str, **overrides) -> ScrapedSeries:
    """Build a ScrapedSeries that the MangaDex scraper would return."""
    base = dict(
        source="mangadex", external_id=external_id, url="",
        title=overrides.get("title", "Death Note"),
        alt_titles=[], summary=None, year=overrides.get("year", 2003),
        status=overrides.get("status", "completed"),
        cover_url=None, authors=[], genres=[], tags=[],
        type="manga",
    )
    return ScrapedSeries(**base)


async def _fake_get_series_async(self, url_or_id: str) -> ScrapedSeries:
    return _fake_scraped(url_or_id)


# ------------------------------------------------------------- add series


@pytest.mark.asyncio
async def test_add_series_from_provider_mangadex(client: AsyncClient) -> None:
    """Patching the class method is the reliable way to fake a remote
    scraper call from inside the API — respx can't intercept the
    shared httpx client once an ASGI app is in play, so we patch at
    the scraper boundary instead.
    """
    from app.scrapers import mangadex as md_module
    orig = md_module.MangaDexScraper.get_series
    md_module.MangaDexScraper.get_series = _fake_get_series_async
    try:
        lib_id = await _make_library()
        r = await client.post("/api/series", json={
            "library_id": lib_id, "provider": "mangadex",
            "external_id": "abc", "run_metadata_refresh": False,
        })
    finally:
        md_module.MangaDexScraper.get_series = orig

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Death Note"
    # The mangadex external id was attached.
    eids = {e["provider"]: e["external_id"] for e in body["external_ids"]}
    assert eids.get("mangadex") == "abc"


@pytest.mark.asyncio
async def test_add_series_unknown_provider(client: AsyncClient) -> None:
    lib_id = await _make_library()
    r = await client.post("/api/series", json={
        "library_id": lib_id, "provider": "doesnotexist",
        "external_id": "x",
    })
    # 400 (ConfigError) via the exception handler.
    assert r.status_code == 400
    assert r.json()["type"] == "config_error"


# ------------------------------------------------------------- follow toggle


@pytest.mark.asyncio
async def test_follow_unfollow(client: AsyncClient) -> None:
    from app.scrapers import mangadex as md_module
    orig = md_module.MangaDexScraper.get_series
    md_module.MangaDexScraper.get_series = _fake_get_series_async
    try:
        lib_id = await _make_library()
        s = (await client.post("/api/series", json={
            "library_id": lib_id, "provider": "mangadex",
            "external_id": "xyz", "run_metadata_refresh": False,
        })).json()
        sid = s["id"]
        assert s["followed"] is False
    finally:
        md_module.MangaDexScraper.get_series = orig

    r = await client.post(f"/api/series/{sid}/follow")
    assert r.status_code == 200
    assert r.json()["followed"] is True

    r = await client.post(f"/api/series/{sid}/unfollow")
    assert r.status_code == 200
    assert r.json()["followed"] is False


# --------------------------------------------------------------- metadata refresh


@pytest.mark.asyncio
async def test_metadata_refresh_merges(client: AsyncClient) -> None:
    from app.metadata import anilist as anilist_module
    from app.metadata import mangadex as md_meta_module
    from app.metadata.base import MetadataRecord

    async def fake_mangadex_record(self, external_id):
        return MetadataRecord(
            provider="mangadex", external_id=external_id,
            title="Naruto", year=1999, status="completed",
            type="manga", country="JP",
        )

    async def no_anilist_record(self, external_id):
        return None

    orig_md = md_meta_module.MangaDexMetadataProvider.get_record
    orig_al = anilist_module.AniListProvider.get_record
    md_meta_module.MangaDexMetadataProvider.get_record = fake_mangadex_record
    anilist_module.AniListProvider.get_record = no_anilist_record
    try:
        lib_id = await _make_library()
        # Add the series first.
        from app.scrapers import mangadex as md_module
        orig_scrape = md_module.MangaDexScraper.get_series
        md_module.MangaDexScraper.get_series = _fake_get_series_async
        try:
            s = (await client.post("/api/series", json={
                "library_id": lib_id, "provider": "mangadex",
                "external_id": "merge-1", "run_metadata_refresh": False,
            })).json()
        finally:
            md_module.MangaDexScraper.get_series = orig_scrape
        sid = s["id"]

        # Metadata refresh — still under the patches.
        r = await client.post(
            f"/api/series/{sid}/metadata/refresh",
            json={"providers": ["mangadex"]},
        )
    finally:
        md_meta_module.MangaDexMetadataProvider.get_record = orig_md
        anilist_module.AniListProvider.get_record = orig_al

    assert r.status_code == 200, r.text
    body = r.json()
    # Mangadex is the only provider; sources_used should reflect that.
    assert "mangadex" in body["sources_used"]
    assert "merged" in body
    assert body["merged"]["title"] == "Naruto"
    assert body["cover_cached"] is False  # no cover URL in our mangadex stub


@pytest.mark.asyncio
async def test_metadata_refresh_with_genres_and_tags(client: AsyncClient) -> None:
    """Regression: a merged record with genres/tags must serialize into
    `SeriesRead` without a 500. Previously `refresh_metadata` built the
    response via `SeriesRead.model_validate(s)`, which raised a
    ValidationError because the ORM exposes genres/tags as rows, not str.
    """
    from app.metadata import anilist as anilist_module
    from app.metadata import mangadex as md_meta_module
    from app.metadata.base import MetadataAuthor, MetadataRecord

    async def fake_mangadex_record(self, external_id):
        return MetadataRecord(
            provider="mangadex", external_id=external_id,
            title="Berserk", year=1989, status="ongoing",
            type="manga", country="JP",
            genres=["Action", "Dark Fantasy"],
            tags=["Demons", "Tragedy"],
            authors=[MetadataAuthor(role="writer", name="Kentaro Miura")],
        )

    async def no_anilist_record(self, external_id):
        return None

    orig_md = md_meta_module.MangaDexMetadataProvider.get_record
    orig_al = anilist_module.AniListProvider.get_record
    md_meta_module.MangaDexMetadataProvider.get_record = fake_mangadex_record
    anilist_module.AniListProvider.get_record = no_anilist_record
    try:
        lib_id = await _make_library("GenresTest")
        from app.scrapers import mangadex as md_module
        orig_scrape = md_module.MangaDexScraper.get_series
        md_module.MangaDexScraper.get_series = _fake_get_series_async
        try:
            s = (await client.post("/api/series", json={
                "library_id": lib_id, "provider": "mangadex",
                "external_id": "berserk-1", "run_metadata_refresh": False,
            })).json()
        finally:
            md_module.MangaDexScraper.get_series = orig_scrape
        sid = s["id"]

        r = await client.post(
            f"/api/series/{sid}/metadata/refresh",
            json={"providers": ["mangadex"]},
        )
    finally:
        md_meta_module.MangaDexMetadataProvider.get_record = orig_md
        anilist_module.AniListProvider.get_record = orig_al

    assert r.status_code == 200, r.text
    body = r.json()
    series = body["series"]
    assert set(series["genres"]) == {"Action", "Dark Fantasy"}
    assert set(series["tags"]) == {"Demons", "Tragedy"}
    assert {"role": "writer", "name": "Kentaro Miura"} in series["authors"]


# ------------------------------------------------------------- backfill


@pytest.mark.asyncio
async def test_backfill_count_query_param(client: AsyncClient) -> None:
    """`POST /backfill?count=2` enqueues only the latest 2 missing chapters."""
    from app.scrapers import mangadex as md_module
    from app.services import downloader

    downloader.reset_for_tests()

    async def fake_get_chapters(self, external_id, *, language=None, limit=500, offset=0):
        return [
            ScrapedChapter(source="mangadex", external_id=f"ch{i}", url="",
                           number=str(i), language="it", volume_number="1")
            for i in (1, 2, 3)
        ]

    orig_series = md_module.MangaDexScraper.get_series
    orig_chapters = md_module.MangaDexScraper.get_chapters
    md_module.MangaDexScraper.get_series = _fake_get_series_async
    md_module.MangaDexScraper.get_chapters = fake_get_chapters
    try:
        lib_id = await _make_library("BackfillTest")
        s = (await client.post("/api/series", json={
            "library_id": lib_id, "provider": "mangadex",
            "external_id": "bf-1", "run_metadata_refresh": False,
        })).json()
        sid = s["id"]
        r = await client.post(f"/api/series/{sid}/backfill?count=2")
    finally:
        md_module.MangaDexScraper.get_series = orig_series
        md_module.MangaDexScraper.get_chapters = orig_chapters
        downloader.reset_for_tests()

    assert r.status_code == 200, r.text
    assert r.json()["scheduled"] == 2


@pytest.mark.asyncio
async def test_backfill_no_provider_returns_400(client: AsyncClient) -> None:
    """A series with no usable provider mapping → clean 400, not a 500."""
    lib_id = await _make_library("NoProv")
    async with session_scope() as s:
        series = Series(library_id=lib_id, title="Orphan", sort_title="Orphan")
        s.add(series)
        await s.flush()
        sid = series.id

    r = await client.post(f"/api/series/{sid}/backfill?count=1")
    assert r.status_code == 400, r.text
    assert r.json()["type"] == "config_error"


# ------------------------------------------------------------- 404


@pytest.mark.asyncio
async def test_get_series_not_found(client: AsyncClient) -> None:
    r = await client.get("/api/series/9999")
    assert r.status_code == 404
    assert r.json()["type"] == "series_not_found"


# ---------------------------------------------------------------- list


@pytest.mark.asyncio
async def test_list_series_filters_by_library(client: AsyncClient) -> None:
    # Two libraries, one series in each.
    from app.models.orm import Series
    lib_a = await _make_library("ListA")
    lib_b = await _make_library("ListB")
    async with session_scope() as s:
        s.add(Series(library_id=lib_a, title="Alpha", sort_title="Alpha"))
        s.add(Series(library_id=lib_b, title="Beta", sort_title="Beta"))

    r = await client.get(f"/api/series?library_id={lib_a}")
    assert r.status_code == 200
    rows = r.json()
    titles = [row["title"] for row in rows]
    assert "Alpha" in titles
    assert "Beta" not in titles
