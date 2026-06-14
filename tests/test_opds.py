"""Tests for the OPDS 1.2 catalog + covers endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from lxml import etree

from app.db.session import session_scope
from app.main import create_app
from app.models.orm import Chapter, Library, Series, Volume
from app.settings import get_settings

ATOM = "http://www.w3.org/2005/Atom"
NS = {"a": ATOM}
# A 2-byte JPEG SOI marker is enough for a content-type check.
_FAKE_IMG = b"\xff\xd8\xff\xe0fake"


@pytest.fixture
async def client():
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _seed(*, with_cover: bool = False, downloaded: bool = True) -> dict:
    cover_path = None
    if with_cover:
        cover = get_settings().covers_path / "berserk.jpg"
        cover.write_bytes(_FAKE_IMG)
        cover_path = str(cover)
    async with session_scope() as s:
        lib = Library(
            name="OpdsLib", type="manga", root_path="/tmp/opds",
            folder_strategy="series_volume_chapter", providers=["mangadex"],
        )
        s.add(lib)
        await s.flush()
        series = Series(
            library_id=lib.id, title="Berserk", sort_title="Berserk",
            language="it", cover_path=cover_path,
        )
        s.add(series)
        await s.flush()
        vol = Volume(series_id=series.id, number="1", sort=1.0, language="it")
        s.add(vol)
        await s.flush()
        ch = Chapter(
            volume_id=vol.id, number="1", sort=1.0, title="Black Swordsman",
            source_provider="mangadex", source_id="c1", language="it",
            pages_count=20, cbz_size=12345,
            file_path=("/data/x.cbz" if downloaded else None),
            downloaded_at=(datetime.now(timezone.utc) if downloaded else None),
        )
        s.add(ch)
        await s.flush()
        return {"lib": lib.id, "series": series.id, "chapter": ch.id}


def _parse(body: bytes) -> etree._Element:
    root = etree.fromstring(body)
    assert root.tag == f"{{{ATOM}}}feed"
    return root


@pytest.mark.asyncio
async def test_opds_root_is_valid_atom(client: AsyncClient) -> None:
    r = await client.get("/opds/v1.2/root")
    assert r.status_code == 200
    assert "atom+xml" in r.headers["content-type"]
    assert "kind=navigation" in r.headers["content-type"]
    root = _parse(r.content)
    titles = [e.text for e in root.findall("a:entry/a:title", NS)]
    assert "Librerie" in titles and "Seguiti" in titles
    # /opds alias also works.
    assert (await client.get("/opds")).status_code == 200


@pytest.mark.asyncio
async def test_opds_navigation_chain(client: AsyncClient) -> None:
    ids = await _seed()

    r = await client.get("/opds/v1.2/libraries")
    root = _parse(r.content)
    hrefs = [link.get("href") for link in root.findall("a:entry/a:link", NS)]
    assert f"/opds/v1.2/libraries/{ids['lib']}" in hrefs

    r = await client.get(f"/opds/v1.2/libraries/{ids['lib']}")
    root = _parse(r.content)
    hrefs = [link.get("href") for link in root.findall("a:entry/a:link", NS)]
    assert f"/opds/v1.2/series/{ids['series']}" in hrefs


@pytest.mark.asyncio
async def test_opds_series_acquisition_feed(client: AsyncClient) -> None:
    ids = await _seed(downloaded=True)
    r = await client.get(f"/opds/v1.2/series/{ids['series']}")
    assert r.status_code == 200
    assert "kind=acquisition" in r.headers["content-type"]
    root = _parse(r.content)
    acq = root.findall(
        "a:entry/a:link[@rel='http://opds-spec.org/acquisition']", NS,
    )
    assert len(acq) == 1
    assert acq[0].get("href") == f"/api/chapters/{ids['chapter']}/file"
    assert acq[0].get("type") == "application/vnd.comicbook+zip"
    assert acq[0].get("length") == "12345"


@pytest.mark.asyncio
async def test_opds_series_skips_undownloaded(client: AsyncClient) -> None:
    ids = await _seed(downloaded=False)
    r = await client.get(f"/opds/v1.2/series/{ids['series']}")
    root = _parse(r.content)
    acq = root.findall("a:entry/a:link[@rel='http://opds-spec.org/acquisition']", NS)
    assert acq == []


@pytest.mark.asyncio
async def test_opds_opensearch_and_search(client: AsyncClient) -> None:
    await _seed()
    r = await client.get("/opds/v1.2/opensearch.xml")
    assert r.status_code == 200
    assert "opensearchdescription" in r.headers["content-type"]
    doc = etree.fromstring(r.content)
    url = doc.find("{http://a9.com/-/spec/opensearch/1.1/}Url")
    assert "{searchTerms}" in url.get("template")

    r = await client.get("/opds/v1.2/search", params={"q": "berserk"})
    root = _parse(r.content)
    titles = [e.text for e in root.findall("a:entry/a:title", NS)]
    assert "Berserk" in titles


# --------------------------------------------------------------- covers


@pytest.mark.asyncio
async def test_cover_served_when_present(client: AsyncClient) -> None:
    ids = await _seed(with_cover=True)
    r = await client.get(f"/api/covers/series/{ids['series']}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content == _FAKE_IMG


@pytest.mark.asyncio
async def test_cover_404_when_absent(client: AsyncClient) -> None:
    ids = await _seed(with_cover=False)
    r = await client.get(f"/api/covers/series/{ids['series']}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cover_404_on_path_traversal(client: AsyncClient) -> None:
    # A cover_path pointing outside the covers cache must not be served.
    outside = get_settings().data_dir / "outside.jpg"
    outside.write_bytes(_FAKE_IMG)
    async with session_scope() as s:
        lib = Library(
            name="OpdsLib2", type="manga", root_path="/tmp/opds2",
            folder_strategy="series_volume_chapter", providers=["mangadex"],
        )
        s.add(lib)
        await s.flush()
        series = Series(
            library_id=lib.id, title="Evil", sort_title="Evil",
            cover_path=str(outside),
        )
        s.add(series)
        await s.flush()
        sid = series.id

    r = await client.get(f"/api/covers/series/{sid}")
    assert r.status_code == 404
