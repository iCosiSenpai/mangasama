"""MangaDex metadata provider tests.

Mirrors the shape of `test_metadata_anilist.py` but for the
`MangaDexMetadataProvider`. We mock the REST endpoint and assert the
parsed `MetadataRecord` matches the contract.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.http_client import get_http
from app.metadata.base import MetadataAuthor
from app.metadata.mangadex import MangaDexMetadataProvider

API = "https://api.mangadex.org"


# ---------------------------------------------------------- fixtures


@pytest.fixture
def provider() -> MangaDexMetadataProvider:
    return MangaDexMetadataProvider(http=get_http())


def _detail_payload() -> dict:
    return {
        "result": "ok",
        "data": {
            "id": "00000000-0000-0000-0000-000000000001",
            "attributes": {
                "title": {"en": "Death Note"},
                "altTitles": [{"ja": "デスノート"}, {"en": "DN"}],
                "description": {"en": "A high school student finds a notebook."},
                "year": 2003,
                "status": "completed",
                "originalLanguage": "ja",
                "lastChapter": "108",
                "lastVolume": "12",
                "publicationDemographic": "shounen",
                "contentRating": "safe",
                "tags": [
                    {"attributes": {"group": "genre", "name": {"en": "Mystery"}}},
                    {"attributes": {"group": "theme", "name": {"en": "Psychological"}}},
                ],
            },
            "relationships": [
                {"id": "a", "type": "author", "attributes": {"name": "Tsugumi Ohba"}},
                {"id": "b", "type": "artist", "attributes": {"name": "Takeshi Obata"}},
                {
                    "id": "c",
                    "type": "cover_art",
                    "attributes": {"fileName": "cover.jpg"},
                },
            ],
        },
    }


def _search_payload() -> dict:
    return {
        "result": "ok",
        "data": [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "attributes": {
                    "title": {"en": "Death Note"},
                    "altTitles": [],
                    "year": 2003,
                    "status": "completed",
                    "originalLanguage": "ja",
                    "tags": [],
                },
                "relationships": [],
            }
        ],
    }


# ---------------------------------------------------------------- search


@pytest.mark.asyncio
@respx.mock
async def test_search_uses_scraper_results(provider: MangaDexMetadataProvider) -> None:
    respx.get(f"{API}/manga").mock(return_value=httpx.Response(200, json=_search_payload()))
    out = await provider.search("death", limit=5, language="en")
    assert len(out) == 1
    cand = out[0]
    assert cand.provider == "mangadex"
    assert cand.external_id == "00000000-0000-0000-0000-000000000001"
    assert cand.title == "Death Note"
    assert cand.cover_url is None  # search payload has no cover
    assert cand.year == 2003


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_empty_on_5xx(provider: MangaDexMetadataProvider) -> None:
    respx.get(f"{API}/manga").mock(return_value=httpx.Response(500, json={"result": "error"}))
    assert await provider.search("death") == []


# ------------------------------------------------------------- get_record


@pytest.mark.asyncio
@respx.mock
async def test_get_record_extracts_fields(provider: MangaDexMetadataProvider) -> None:
    respx.get(f"{API}/manga/00000000-0000-0000-0000-000000000001").mock(
        return_value=httpx.Response(200, json=_detail_payload()),
    )
    rec = await provider.get_record("00000000-0000-0000-0000-000000000001")
    assert rec.provider == "mangadex"
    assert rec.title == "Death Note"
    assert rec.year == 2003
    assert rec.status == "completed"
    assert rec.country == "ja"
    assert rec.type == "manga"
    assert rec.cover_url == "https://uploads.mangadex.org/covers/c/cover.jpg"
    # Genres vs tags.
    assert "Mystery" in rec.genres
    assert "Psychological" in rec.tags
    # Authors.
    roles = {(a.role, a.name) for a in rec.authors}
    assert ("writer", "Tsugumi Ohba") in roles
    assert ("penciller", "Takeshi Obata") in roles
    # Confidence.
    assert rec.confidence == 0.85
    # Mangadex-specific metadata preserved.
    assert rec.metadata["lastChapter"] == "108"
    assert rec.metadata["demographic"] == "shounen"


@pytest.mark.asyncio
async def test_get_record_rejects_non_uuid(provider: MangaDexMetadataProvider) -> None:
    from app.scrapers.base import SeriesNotFound
    with pytest.raises(SeriesNotFound):
        await provider.get_record("not-a-uuid")


@pytest.mark.asyncio
@respx.mock
async def test_get_record_raises_when_no_data(provider: MangaDexMetadataProvider) -> None:
    respx.get(f"{API}/manga/00000000-0000-0000-0000-000000000001").mock(
        return_value=httpx.Response(200, json={"result": "ok", "data": None}),
    )
    from app.scrapers.base import SeriesNotFound
    with pytest.raises(SeriesNotFound):
        await provider.get_record("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------- health


@pytest.mark.asyncio
@respx.mock
async def test_health_check_pings(provider: MangaDexMetadataProvider) -> None:
    respx.get(f"{API}/ping").mock(return_value=httpx.Response(200, text="pong"))
    assert await provider.health_check() is True


@pytest.mark.asyncio
@respx.mock
async def test_health_check_handles_500(provider: MangaDexMetadataProvider) -> None:
    respx.get(f"{API}/ping").mock(return_value=httpx.Response(500, text="boom"))
    assert await provider.health_check() is False
