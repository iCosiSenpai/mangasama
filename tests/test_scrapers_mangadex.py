"""MangaDex scraper tests using respx to mock httpx.

The MangaDex API is fully public and doesn't need auth, so we can
construct a realistic minimal payload and assert our parser extracts
the right dataclasses.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.core.exceptions import SourceUnavailable
from app.scrapers.mangadex import MangaDexScraper

API = "https://api.mangadex.org"


# ---------------------------------------------------------- fixtures / helpers


@pytest.fixture
def scraper() -> MangaDexScraper:
    from app.core.http_client import get_http
    # Use the shared singleton so the autouse `_http_client` fixture
    # already started it. respx intercepts the transport on the way out.
    return MangaDexScraper(http=get_http())


def _search_payload() -> dict:
    return {
        "result": "ok",
        "data": [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "attributes": {
                    "title": {"en": "Death Note"},
                    "altTitles": [{"ja": "デスノート"}],
                    "description": {"en": "A high school student finds a notebook."},
                    "year": 2003,
                    "status": "completed",
                    "originalLanguage": "ja",
                    "tags": [
                        # MangaDex tags localize `name` by language.
                        {
                            "attributes": {
                                "group": "genre",
                                "name": {"en": "Mystery"},
                            },
                        },
                        {
                            "attributes": {
                                "group": "theme",
                                "name": {"en": "Psychological"},
                            },
                        },
                    ],
                },
                "relationships": [
                    {
                        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
                        "type": "author",
                        "attributes": {"name": "Tsugumi Ohba"},
                    },
                    {
                        "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1",
                        "type": "artist",
                        "attributes": {"name": "Takeshi Obata"},
                    },
                    {
                        "id": "cccccccc-cccc-cccc-cccc-cccccccccc01",
                        "type": "cover_art",
                        "attributes": {"fileName": "cover.jpg"},
                    },
                ],
            }
        ],
    }


def _detail_payload() -> dict:
    return {
        "result": "ok",
        "data": {
            "id": "00000000-0000-0000-0000-000000000001",
            "attributes": {
                "title": {"en": "Death Note"},
                "description": {"en": "A high school student finds a notebook."},
                "year": 2003,
                "status": "completed",
                "originalLanguage": "ja",
                "lastChapter": "108",
                "lastVolume": "12",
            },
            "relationships": [
                {
                    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
                    "type": "author",
                    "attributes": {"name": "Tsugumi Ohba"},
                },
            ],
        },
    }


def _chapters_payload() -> dict:
    return {
        "result": "ok",
        "data": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "attributes": {
                    "chapter": "1",
                    "title": "Death",
                    "translatedLanguage": "en",
                    "volume": "1",
                    "pages": 25,
                    "publishedAt": "2024-01-01T00:00:00+00:00",
                },
                "relationships": [
                    {
                        "id": "ssssssss-ssss-ssss-ssss-sssssssssss1",
                        "type": "scanlation_group",
                        "attributes": {"name": "MangaGroup"},
                    },
                ],
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "attributes": {
                    "chapter": "1",
                    "title": "Ryuk",
                    "translatedLanguage": "it",
                    "volume": "1",
                    "pages": 30,
                    "publishedAt": "2024-01-02T00:00:00+00:00",
                },
                "relationships": [],
            },
        ],
    }


def _at_home_payload() -> dict:
    return {
        "result": "ok",
        "baseUrl": "https://cdn.mangadex.org",
        "chapter": {
            "hash": "abc123def456",
            "data": ["page1.jpg", "page2.jpg", "page3.jpg"],
            "dataSaver": ["page1s.jpg", "page2s.jpg", "page3s.jpg"],
        },
    }


# ----------------------------------------------------------------------- search


@pytest.mark.asyncio
@respx.mock
async def test_search_parses_results(scraper: MangaDexScraper) -> None:
    respx.get(f"{API}/manga").mock(
        return_value=httpx.Response(200, json=_search_payload())
    )
    out = await scraper.search("death", limit=10)
    assert len(out) == 1
    s = out[0]
    assert s.title == "Death Note"
    assert s.source == "mangadex"
    assert s.external_id == "00000000-0000-0000-0000-000000000001"
    assert s.type == "manga"
    assert s.year == 2003
    assert s.status == "completed"
    assert ("writer", "Tsugumi Ohba") in s.authors
    assert ("penciller", "Takeshi Obata") in s.authors
    # Genres vs tags split: "Mystery" is a genre, "Psychological" is a tag.
    assert "Mystery" in s.genres
    assert "Psychological" in s.tags
    assert s.cover_url is not None
    assert s.cover_url.endswith("/cover.jpg")


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_empty_on_5xx(scraper: MangaDexScraper) -> None:
    respx.get(f"{API}/manga").mock(
        return_value=httpx.Response(500, json={"result": "error"})
    )
    # max_retries=0 means we don't loop; the 500 surfaces as SourceUnavailable
    # which `search` swallows and returns [].
    out = await scraper.search("death")
    assert out == []


# --------------------------------------------------------------------- get_series


@pytest.mark.asyncio
@respx.mock
async def test_get_series_by_id(scraper: MangaDexScraper) -> None:
    respx.get(f"{API}/manga/00000000-0000-0000-0000-000000000001").mock(
        return_value=httpx.Response(200, json=_detail_payload())
    )
    s = await scraper.get_series("00000000-0000-0000-0000-000000000001")
    assert s.title == "Death Note"
    assert s.metadata["lastChapter"] == "108"
    assert s.metadata["lastVolume"] == "12"


@pytest.mark.asyncio
@respx.mock
async def test_get_series_accepts_full_url(scraper: MangaDexScraper) -> None:
    route = respx.get(f"{API}/manga/00000000-0000-0000-0000-000000000001").mock(
        return_value=httpx.Response(200, json=_detail_payload())
    )
    s = await scraper.get_series(
        "https://mangadex.org/title/00000000-0000-0000-0000-000000000001"
    )
    assert s.external_id == "00000000-0000-0000-0000-000000000001"
    assert route.called


@pytest.mark.asyncio
async def test_get_series_raises_on_bad_id(scraper: MangaDexScraper) -> None:
    from app.scrapers.base import SeriesNotFound
    with pytest.raises(SeriesNotFound):
        await scraper.get_series("not-a-uuid-or-url")


# -------------------------------------------------------------------- chapters


@pytest.mark.asyncio
@respx.mock
async def test_get_chapters_uses_italian_first_then_english(scraper: MangaDexScraper) -> None:
    route = respx.get(f"{API}/manga/00000000-0000-0000-0000-000000000001/feed").mock(
        return_value=httpx.Response(200, json=_chapters_payload())
    )
    out = await scraper.get_chapters(
        "00000000-0000-0000-0000-000000000001", language="it",
    )
    assert len(out) == 2
    # We requested "it" first, but MangaDex returns en + it mixed in the feed
    # because we asked for ["it", "en"] internally. The Italian chapter should
    # be present.
    langs = {c.language for c in out}
    assert "it" in langs
    assert "en" in langs
    # And the URL params actually used both languages. httpx's URL.params
    # collapses repeated keys in `.items()`; use `multi_items()` to get
    # every (key, value) pair in order.
    assert route.called
    sent = route.calls.last.request.url.params
    sent_langs = [
        v for k, v in sent.multi_items() if "translatedLanguage" in k
    ]
    assert sent_langs == ["it", "en"]


# ----------------------------------------------------------------------- pages


@pytest.mark.asyncio
@respx.mock
async def test_get_pages_builds_data_urls(scraper: MangaDexScraper) -> None:
    respx.get(f"{API}/at-home/server/11111111-1111-1111-1111-111111111111").mock(
        return_value=httpx.Response(200, json=_at_home_payload())
    )
    pages = await scraper.get_pages("11111111-1111-1111-1111-111111111111")
    assert [p.index for p in pages] == [0, 1, 2]
    assert pages[0].url == "https://cdn.mangadex.org/data/abc123def456/page1.jpg"
    assert pages[2].url == "https://cdn.mangadex.org/data/abc123def456/page3.jpg"


@pytest.mark.asyncio
async def test_get_pages_returns_empty_for_bad_id(scraper: MangaDexScraper) -> None:
    out = await scraper.get_pages("")
    assert out == []
    out = await scraper.get_pages("not-a-uuid")
    assert out == []


# --------------------------------------------------------------------- health


@pytest.mark.asyncio
@respx.mock
async def test_health_check_pings(scraper: MangaDexScraper) -> None:
    respx.get(f"{API}/ping").mock(return_value=httpx.Response(200, text="pong"))
    assert await scraper.health_check() is True


@pytest.mark.asyncio
@respx.mock
async def test_health_check_handles_500(scraper: MangaDexScraper) -> None:
    respx.get(f"{API}/ping").mock(return_value=httpx.Response(500, text="oops"))
    assert await scraper.health_check() is False


# --------------------------------------------------------------- language map


def test_original_language_maps_to_type() -> None:
    assert MangaDexScraper._map_type("ja") == "manga"
    assert MangaDexScraper._map_type("ko") == "manhwa"
    assert MangaDexScraper._map_type("zh") == "manhua"
    assert MangaDexScraper._map_type(None) == "manga"
    assert MangaDexScraper._map_type("xx") == "manga"  # unknown -> manga


def test_extract_id_handles_uuid_and_url() -> None:
    uid = "00000000-0000-0000-0000-000000000001"
    assert MangaDexScraper._extract_id(uid) == uid
    assert MangaDexScraper._extract_id(f"https://mangadex.org/title/{uid}") == uid
    assert MangaDexScraper._extract_id("") == ""
    assert MangaDexScraper._extract_id("garbage") == ""
