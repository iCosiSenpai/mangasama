"""MangaWorld scraper tests using respx with inline HTML fixtures.

We test the *parser* end-to-end: an HTTP mock returns realistic
fragmented HTML, and we assert the dataclass output. No real network
calls. The fixtures mirror the structure we saw on the live site
(see the module docstring of `app.scrapers.mangaworld.py`).
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.exceptions import BlockedByCloudflare
from app.core.http_client import get_http
from app.scrapers.mangaworld import MangaWorldScraper

BASE = "https://www.mangaworld.mx"


# --------------------------------------------------------- HTML fixtures


def _manga_page_html() -> str:
    return """<!doctype html>
<html><head><title>99 Reinforced Wooden Stick - MangaWorld</title></head><body>
  <div class="thumb mb-3 text-center">
    <img class="rounded" src="https://cdn.mangaworld.mx/mangas/abc123.jpg"
         alt="99 Reinforced Wooden Stick Scan ITA" />
  </div>
  <div class="info">
    <h1 class="name bigger">99 Reinforced Wooden Stick</h1>
    <div class="meta-data row px-1">
      <div class="col-12">
        <span class="font-weight-bold">Titoli alternativi: </span>
        +99 Wooden Stick, 99 Hardened Wooden Stick, 99强化木棍
      </div>
      <div class="col-12">
        <span class="font-weight-bold">Generi: </span>
        <a href="?genre=azione" class="badge badge-primary">Azione</a>
        <a href="?genre=drammatico" class="badge badge-primary">Drammatico</a>
        <a href="?genre=shounen" class="badge badge-primary">Shounen</a>
      </div>
      <div class="col-12 col-md-6">
        <span class="font-weight-bold">Autore: </span>
        <a href="?author=Hongsil">Hongsil</a>
      </div>
      <div class="col-12 col-md-6">
        <span class="font-weight-bold">Artista: </span>
        <a href="?artist=Jipery">Jipery</a>
      </div>
      <div class="col-12 col-md-6">
        <span class="font-weight-bold">Tipo: </span>
        <a href="?type=manhwa">Manhwa</a>
      </div>
      <div class="col-12 col-md-6">
        <span class="font-weight-bold">Stato: </span>
        <a href="?status=dropped">Droppato</a>
      </div>
      <div class="col-12 col-md-6">
        <span class="font-weight-bold">Anno di uscita: </span>
        <a href="?year=2022">2022</a>
      </div>
    </div>
  </div>
  <div class="chapters-wrapper py-2 pl-0">
    <div class="chapter pl-2">
      <a class="chap" href="/manga/2906/99-reinforced-wooden-stick/read/646cf72fa8b100502bd014ed?style=list"
         title="Capitolo 15">
        <span class="d-inline-block">Capitolo 15</span>
        <i class="text-right text-muted chap-date">23 Maggio 2023</i>
      </a>
    </div>
    <div class="chapter pl-2">
      <a class="chap" href="/manga/2906/99-reinforced-wooden-stick/read/63e28c7ed2b8a617cd121e16?style=list"
         title="Capitolo 14">
        <span class="d-inline-block">Capitolo 14</span>
        <i class="text-right text-muted chap-date">07 Febbraio 2023</i>
      </a>
    </div>
    <div class="chapter pl-2">
      <a class="chap" href="/manga/2906/99-reinforced-wooden-stick/read/63c0174d76c0d6106ebf12a6?style=list"
         title="Capitolo 13">
        <span class="d-inline-block">Capitolo 13</span>
        <i class="text-right text-muted chap-date">12 Gennaio 2023</i>
      </a>
    </div>
  </div>
</body></html>"""


def _archive_html() -> str:
    return """<!doctype html>
<html><body>
  <div class="entry">
    <a href="/manga/2906/99-reinforced-wooden-stick">
      <img src="https://cdn.mangaworld.mx/mangas/abc123.jpg" />
    </a>
    <div class="name"><a href="/manga/2906/99-reinforced-wooden-stick">99 Reinforced Wooden Stick</a></div>
    <div class="type">Manhwa</div>
    <div class="status">Droppato</div>
    <div class="genre">Azione</div>
    <div class="genre">Drammatico</div>
  </div>
  <div class="entry">
    <a href="/manga/325">
      <img src="https://cdn.mangaworld.mx/mangas/def456.jpg" />
    </a>
    <div class="name"><a href="/manga/325">Traeh</a></div>
    <div class="type">Manhua</div>
    <div class="status">In corso</div>
  </div>
  <div class="entry">
    <a href="/manga/2000/one-piece">
      <img src="https://cdn.mangaworld.mx/mangas/op.jpg" />
    </a>
    <div class="name"><a href="/manga/2000/one-piece">One Piece</a></div>
    <div class="type">Manga</div>
    <div class="status">In corso</div>
  </div>
</body></html>"""


def _chapter_reader_html() -> str:
    return """<!doctype html>
<html><body>
  <div id="reader">
    <img id="page-0" class="page-image img-fluid"
         src="https://cdn.mangaworld.mx/chapters/99-reinforced-wooden-stick/cap-15/1.jpg" />
    <img id="page-1" class="page-image img-fluid"
         src="https://cdn.mangaworld.mx/chapters/99-reinforced-wooden-stick/cap-15/2.jpg" />
    <img id="page-2" class="page-image img-fluid"
         src="https://cdn.mangaworld.mx/chapters/99-reinforced-wooden-stick/cap-15/3.jpg" />
  </div>
</body></html>"""


# ----------------------------------------------------------------- fixtures


@pytest.fixture
def scraper() -> MangaWorldScraper:
    return MangaWorldScraper(http=get_http())


# -------------------------------------------------------------- extract_id


def test_extract_id_handles_various_inputs() -> None:
    assert MangaWorldScraper._extract_id("2906") == "2906"
    assert MangaWorldScraper._extract_id("/manga/2906") == "2906"
    assert MangaWorldScraper._extract_id("/manga/2906/99-reinforced-wooden-stick/read/abc?style=list") == "2906"
    assert MangaWorldScraper._extract_id("https://www.mangaworld.mx/manga/2906/99-reinforced-wooden-stick") == "2906"
    assert MangaWorldScraper._extract_id("") == ""
    assert MangaWorldScraper._extract_id("not-a-number") == ""


# ------------------------------------------------------- date / number helpers


def test_parse_chapter_number() -> None:
    assert MangaWorldScraper._parse_chapter_number("Capitolo 15") == "15"
    assert MangaWorldScraper._parse_chapter_number("Capitolo 12.5") == "12.5"
    assert MangaWorldScraper._parse_chapter_number("Capitolo Extra 3") == "3"
    assert MangaWorldScraper._parse_chapter_number("") == "0"


def test_parse_italian_date() -> None:
    from datetime import datetime
    d = MangaWorldScraper._parse_italian_date("23 Maggio 2023")
    assert d == datetime(2023, 5, 23)
    assert MangaWorldScraper._parse_italian_date("07 Febbraio 2023") == datetime(2023, 2, 7)
    assert MangaWorldScraper._parse_italian_date("not a date") is None
    assert MangaWorldScraper._parse_italian_date("") is None


# ----------------------------------------------------------------- search


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_matching_cards(scraper: MangaWorldScraper) -> None:
    respx.get(f"{BASE}/archive").mock(return_value=httpx.Response(200, text=_archive_html()))
    out = await scraper.search("one piece", limit=10)
    assert len(out) == 1
    s = out[0]
    assert s.title == "One Piece"
    assert s.external_id == "2000"
    assert s.type == "manga"
    assert s.status == "ongoing"
    assert s.cover_url and s.cover_url.endswith("op.jpg")


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_empty_when_no_match(scraper: MangaWorldScraper) -> None:
    respx.get(f"{BASE}/archive").mock(return_value=httpx.Response(200, text=_archive_html()))
    out = await scraper.search("zzz nonexistent", limit=10)
    assert out == []


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_all_when_no_query(scraper: MangaWorldScraper) -> None:
    respx.get(f"{BASE}/archive").mock(return_value=httpx.Response(200, text=_archive_html()))
    out = await scraper.search("", limit=10)
    # All three cards.
    assert {s.title for s in out} == {
        "99 Reinforced Wooden Stick", "Traeh", "One Piece",
    }


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_empty_on_cloudflare_403(scraper: MangaWorldScraper) -> None:
    respx.get(f"{BASE}/archive").mock(return_value=httpx.Response(403, text="blocked"))
    out = await scraper.search("anything")
    assert out == []


# -------------------------------------------------------------- get_series


@pytest.mark.asyncio
@respx.mock
async def test_get_series_extracts_all_fields(scraper: MangaWorldScraper) -> None:
    respx.get(f"{BASE}/manga/2906").mock(return_value=httpx.Response(200, text=_manga_page_html()))
    s = await scraper.get_series("2906")
    assert s.source == "mangaworld"
    assert s.external_id == "2906"
    assert s.title == "99 Reinforced Wooden Stick"
    assert s.year == 2022
    assert s.type == "manhwa"
    assert s.status == "cancelled"   # "Droppato" -> cancelled per our map
    assert s.cover_url == "https://cdn.mangaworld.mx/mangas/abc123.jpg"
    # Authors
    roles = {role: name for role, name in s.authors}
    assert roles.get("writer") == "Hongsil"
    assert roles.get("penciller") == "Jipery"
    # Genres (extracted from `.badge.badge-primary`)
    assert "Azione" in s.genres
    assert "Drammatico" in s.genres
    assert "Shounen" in s.genres
    # Alt titles
    assert any("99 Wooden Stick" in a for a in s.alt_titles)
    assert any("99强化木棍" in a for a in s.alt_titles)


@pytest.mark.asyncio
async def test_get_series_raises_on_bad_id(scraper: MangaWorldScraper) -> None:
    from app.scrapers.base import SeriesNotFound
    with pytest.raises(SeriesNotFound):
        await scraper.get_series("")


# -------------------------------------------------------------- get_chapters


@pytest.mark.asyncio
@respx.mock
async def test_get_chapters_parsed_in_chronological_order(scraper: MangaWorldScraper) -> None:
    """MangaWorld lists newest first; we reverse so the output is oldest first."""
    respx.get(f"{BASE}/manga/2906").mock(return_value=httpx.Response(200, text=_manga_page_html()))
    out = await scraper.get_chapters("2906", language="it")
    assert len(out) == 3
    # The order in the HTML is 15, 14, 13; we return 13, 14, 15.
    assert [c.number for c in out] == ["13", "14", "15"]
    # Every chapter is Italian (MangaWorld only ships IT).
    assert all(c.language == "it" for c in out)
    # The first chapter's published date is the oldest.
    assert out[0].published_at is not None
    assert out[0].published_at.year == 2023
    # The external_id is a full URL with style=list (used to fetch pages).
    assert "style=list" in out[0].external_id
    assert "mangaworld.mx" in out[0].external_id


@pytest.mark.asyncio
async def test_get_chapters_returns_empty_for_bad_id(scraper: MangaWorldScraper) -> None:
    assert await scraper.get_chapters("") == []


# ------------------------------------------------------------------ pages


@pytest.mark.asyncio
@respx.mock
async def test_get_pages_returns_ordered_list(scraper: MangaWorldScraper) -> None:
    chap_url = (
        f"{BASE}/manga/2906/99-reinforced-wooden-stick/read/abc?style=list"
    )
    respx.get(chap_url).mock(return_value=httpx.Response(200, text=_chapter_reader_html()))
    out = await scraper.get_pages(chap_url)
    assert [p.index for p in out] == [0, 1, 2]
    assert all("cdn.mangaworld.mx" in p.url for p in out)


@pytest.mark.asyncio
@respx.mock
async def test_get_pages_appends_style_list_if_missing(scraper: MangaWorldScraper) -> None:
    """If the caller passes a chapter URL without `?style=list`, we add it."""
    url_without = f"{BASE}/manga/2906/read/abc"
    respx.get(url_without).mock(return_value=httpx.Response(200, text=_chapter_reader_html()))
    out = await scraper.get_pages(url_without)
    # And the request was made with `?style=list`.
    assert respx.calls.last.request.url.params.get("style") == "list"
    assert len(out) == 3


@pytest.mark.asyncio
async def test_get_pages_returns_empty_for_empty_input(scraper: MangaWorldScraper) -> None:
    assert await scraper.get_pages("") == []


@pytest.mark.asyncio
@respx.mock
async def test_get_pages_returns_empty_on_cloudflare(scraper: MangaWorldScraper) -> None:
    respx.get(f"{BASE}/manga/2906/read/abc?style=list").mock(
        return_value=httpx.Response(403, text="blocked"),
    )
    out = await scraper.get_pages(f"{BASE}/manga/2906/read/abc?style=list")
    assert out == []


# --------------------------------------------------------- health_check


@pytest.mark.asyncio
@respx.mock
async def test_health_check_returns_true_on_200(scraper: MangaWorldScraper) -> None:
    respx.get(f"{BASE}/").mock(
        return_value=httpx.Response(200, text="<html><title>MangaWorld - Manga Scan ITA</title></html>"),
    )
    assert await scraper.health_check() is True


@pytest.mark.asyncio
@respx.mock
async def test_health_check_returns_false_on_403(scraper: MangaWorldScraper) -> None:
    respx.get(f"{BASE}/").mock(return_value=httpx.Response(403, text="blocked"))
    assert await scraper.health_check() is False
