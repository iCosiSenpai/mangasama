"""AniList metadata provider tests.

We mock the GraphQL endpoint with respx. The fixtures are minimal
but realistic; the parser is tested end-to-end.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.http_client import get_http
from app.metadata.anilist import AniListProvider

API = "https://graphql.anilist.co"


# ---------------------------------------------------------- fixtures


@pytest.fixture
def provider() -> AniListProvider:
    return AniListProvider(http=get_http())


def _gql_response(data: dict, errors: list | None = None) -> dict:
    return {"data": data, "errors": errors or []}


def _search_payload() -> dict:
    return _gql_response({
        "Page": {
            "media": [
                {
                    "id": 1,
                    "siteUrl": "https://anilist.co/manga/1",
                    "title": {"romaji": "NARUTO", "english": "Naruto", "native": "ナルト"},
                    "startDate": {"year": 1999},
                    "coverImage": {
                        "extraLarge": "https://img.anilist.co/large/1.jpg",
                        "large": "https://img.anilist.co/l/1.jpg",
                        "color": "#ff0000",
                    },
                    "countryOfOrigin": "JP",
                    "genres": ["Action", "Adventure"],
                    "tags": [{"name": "Ninja"}, {"name": "Shounen"}],
                    "chapters": 700,
                    "volumes": 72,
                    "status": "FINISHED",
                },
                {
                    "id": 2,
                    "siteUrl": "https://anilist.co/manga/2",
                    "title": {"romaji": "Boruto"},
                    "startDate": {"year": 2016},
                    "coverImage": {"extraLarge": "https://img.anilist.co/large/2.jpg"},
                    "countryOfOrigin": "JP",
                    "genres": ["Action"],
                    "tags": [],
                    "chapters": 80,
                    "volumes": 20,
                    "status": "RELEASING",
                },
            ],
        },
    })


def _detail_payload() -> dict:
    return _gql_response({
        "Media": {
            "id": 1,
            "siteUrl": "https://anilist.co/manga/1",
            "title": {"romaji": "NARUTO", "english": "Naruto", "native": "ナルト"},
            "description": "<p>A young ninja <b>seeking recognition</b>.</p>",
            "coverImage": {"extraLarge": "https://img.anilist.co/large/1.jpg"},
            "startDate": {"year": 1999},
            "endDate": {"year": 2014},
            "status": "FINISHED",
            "chapters": 700,
            "volumes": 72,
            "countryOfOrigin": "JP",
            "format": "MANGA",
            "genres": ["Action", "Adventure", "Martial Arts"],
            "tags": [{"name": "Ninja"}, {"name": "Shounen"}],
            "staff": {
                "edges": [
                    {"role": "Story", "node": {"name": {"full": "Masashi Kishimoto"}}},
                    {"role": "Art", "node": {"name": {"full": "Masashi Kishimoto"}}},
                    {"role": "Cover", "node": {"name": {"full": "Someone Else"}}},
                ],
            },
            "idMal": 11,
        },
    })


# ---------------------------------------------------------------- search


@pytest.mark.asyncio
@respx.mock
async def test_search_parses_candidates(provider: AniListProvider) -> None:
    respx.post(API).mock(return_value=httpx.Response(200, json=_search_payload()))
    out = await provider.search("naruto", limit=10)
    assert len(out) == 2
    first = out[0]
    assert first.provider == "anilist"
    assert first.external_id == "1"
    assert first.title == "Naruto"  # english wins over romaji
    assert "NARUTO" in first.alt_titles or "ナルト" in first.alt_titles
    assert first.year == 1999
    assert first.cover_url == "https://img.anilist.co/large/1.jpg"
    # The metadata carries a few extras.
    assert first.metadata["chapters"] == 700
    assert first.metadata["country"] == "JP"


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_empty_on_5xx(provider: AniListProvider) -> None:
    respx.post(API).mock(return_value=httpx.Response(500, json={"errors": ["boom"]}))
    assert await provider.search("anything") == []


# ------------------------------------------------------------- get_record


@pytest.mark.asyncio
@respx.mock
async def test_get_record_extracts_all_fields(provider: AniListProvider) -> None:
    respx.post(API).mock(return_value=httpx.Response(200, json=_detail_payload()))
    rec = await provider.get_record("1")
    assert rec.provider == "anilist"
    assert rec.external_id == "1"
    assert rec.title == "Naruto"
    # Summary is HTML-stripped + whitespace-collapsed.
    assert rec.summary is not None
    assert "<p>" not in rec.summary
    assert "<b>" not in rec.summary
    assert "young ninja" in rec.summary
    assert "seeking recognition" in rec.summary
    # Year.
    assert rec.year == 1999
    # Status mapping.
    assert rec.status == "completed"
    # Country + type.
    assert rec.country == "JP"
    assert rec.type == "manga"
    # Cover.
    assert rec.cover_url == "https://img.anilist.co/large/1.jpg"
    # Genres + tags.
    assert "Action" in rec.genres
    assert "Martial Arts" in rec.genres
    assert "Ninja" in rec.tags
    # Authors — role mapping: Story -> writer, Art -> penciller, Cover -> cover_artist.
    roles = {(a.role, a.name) for a in rec.authors}
    assert ("writer", "Masashi Kishimoto") in roles
    assert ("penciller", "Masashi Kishimoto") in roles
    assert ("cover_artist", "Someone Else") in roles
    # Confidence.
    assert rec.confidence == 0.9
    # AniList's idMal is in metadata.
    assert rec.metadata["idMal"] == 11


@pytest.mark.asyncio
async def test_get_record_rejects_non_numeric_id(provider: AniListProvider) -> None:
    with pytest.raises(ValueError):
        await provider.get_record("not-a-number")


@pytest.mark.asyncio
@respx.mock
async def test_get_record_raises_when_no_media(provider: AniListProvider) -> None:
    respx.post(API).mock(return_value=httpx.Response(200, json=_gql_response({"Media": None})))
    from app.core.exceptions import SourceUnavailable
    with pytest.raises(SourceUnavailable):
        await provider.get_record("99999")


# ---------------------------------------------------------------- health


@pytest.mark.asyncio
@respx.mock
async def test_health_check_returns_true_on_200(provider: AniListProvider) -> None:
    respx.post(API).mock(return_value=httpx.Response(200, json={"data": {"Viewer": {"id": 1}}}))
    assert await provider.health_check() is True


@pytest.mark.asyncio
@respx.mock
async def test_health_check_returns_false_on_5xx(provider: AniListProvider) -> None:
    respx.post(API).mock(return_value=httpx.Response(500, json={"errors": ["oops"]}))
    assert await provider.health_check() is False
