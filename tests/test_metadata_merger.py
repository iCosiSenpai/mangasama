"""Tests for the `MetadataMerger`.

Pure-function tests: we build `MetadataRecord`s by hand and assert
the merged result. No HTTP, no DB.
"""

from __future__ import annotations

import pytest

from app.metadata.anilist import AniListProvider
from app.metadata.base import MetadataAuthor, MetadataRecord
from app.metadata.merger import MergedMetadata, MetadataMerger


def _rec(
    provider: str,
    *,
    confidence: float = 0.8,
    title: str = "",
    alt_titles: list[str] | None = None,
    summary: str | None = None,
    year: int | None = None,
    status: str | None = None,
    cover_url: str | None = None,
    country: str | None = None,
    type: str | None = None,
    authors: list[MetadataAuthor] | None = None,
    genres: list[str] | None = None,
    tags: list[str] | None = None,
    publisher: str | None = None,
    metadata: dict | None = None,
) -> MetadataRecord:
    return MetadataRecord(
        provider=provider,  # type: ignore[arg-type]
        external_id=f"{provider}-1",
        title=title, alt_titles=alt_titles or [], summary=summary,
        year=year, status=status, cover_url=cover_url, country=country,
        type=type, authors=authors or [], genres=genres or [],
        tags=tags or [], publisher=publisher, metadata=metadata or {},
        confidence=confidence,
    )


# ----------------------------------------------------------- empty input


def test_merge_empty_returns_empty() -> None:
    m = MetadataMerger().merge([])
    assert isinstance(m, MergedMetadata)
    assert m.title == ""
    assert m.source_records == []
    assert m.confidence == 0.0


# ---------------------------------------------------------------- title


def test_title_picks_longest_non_empty() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", title="Naruto"),
        _rec("anilist", title="NARUTO -ナルト-", confidence=0.9),
    ])
    assert m.title == "NARUTO -ナルト-"
    assert m.attribution["title"] == "anilist"


def test_title_falls_back_to_single_provider() -> None:
    m = MetadataMerger().merge([_rec("mangadex", title="Only")])
    assert m.title == "Only"
    assert m.attribution["title"] == "mangadex"


# --------------------------------------------------------------- summary


def test_summary_picks_longest() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", summary="Short.", confidence=0.8),
        _rec("anilist", summary="A long and detailed summary that wins.", confidence=0.9),
    ])
    assert m.summary == "A long and detailed summary that wins."
    assert m.attribution["summary"] == "anilist"


# ------------------------------------------------------------------ year


def test_year_is_median() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", year=1999),
        _rec("anilist", year=2000),
        _rec("google_books", year=2001),
    ])
    assert m.year == 2000


def test_year_skips_none() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", year=1999),
        _rec("anilist", year=None),
    ])
    assert m.year == 1999


# ------------------------------------------------------------------ cover


def test_cover_picks_highest_confidence() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", cover_url="https://mangadex/cover.jpg", confidence=0.85),
        _rec("anilist", cover_url="https://anilist/cover.jpg", confidence=0.9),
    ])
    assert m.cover_url == "https://anilist/cover.jpg"
    assert m.attribution["cover_url"] == "anilist"


def test_cover_falls_back_to_lower_confidence() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", cover_url="https://mangadex/cover.jpg", confidence=0.85),
        _rec("anilist", cover_url=None, confidence=0.9),
    ])
    assert m.cover_url == "https://mangadex/cover.jpg"
    assert m.attribution["cover_url"] == "mangadex"


def test_cover_preferred_override() -> None:
    m = MetadataMerger().merge(
        [
            _rec("mangadex", cover_url="https://mangadex/cover.jpg", confidence=0.85),
            _rec("anilist", cover_url="https://anilist/cover.jpg", confidence=0.9),
        ],
        preferred_cover="mangadex",
    )
    assert m.cover_url == "https://mangadex/cover.jpg"
    assert m.attribution["cover_url"] == "mangadex"


# --------------------------------------------------------------- status


def test_status_picks_consensus() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", status="ongoing", confidence=0.85),
        _rec("anilist", status="ongoing", confidence=0.9),
    ])
    assert m.status == "ongoing"
    assert m.attribution["status"] == "anilist"


def test_status_picks_highest_confidence_on_conflict() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", status="completed", confidence=0.85),
        _rec("anilist", status="ongoing", confidence=0.9),
    ])
    # AniList is highest-confidence, "ongoing" wins.
    assert m.status == "ongoing"
    assert m.attribution["status"] == "anilist"


# ------------------------------------------------------------------ type


def test_type_consensus() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", type="manhwa"),
        _rec("anilist", type="manhwa", confidence=0.9),
    ])
    assert m.type == "manhwa"


def test_type_country_mapping_proxy() -> None:
    # No type in the record, but country=JP -> we'd usually derive it
    # upstream. The merger doesn't infer from country; it only votes
    # on explicit `type`.
    m = MetadataMerger().merge([
        _rec("mangadex", type=None, country="JP"),
    ])
    assert m.type is None


# ---------------------------------------------------------------- authors


def test_authors_union_across_providers() -> None:
    m = MetadataMerger().merge([
        _rec(
            "mangadex",
            authors=[MetadataAuthor(role="writer", name="Ohba")],
        ),
        _rec(
            "anilist",
            authors=[MetadataAuthor(role="penciller", name="Obata")],
            confidence=0.9,
        ),
    ])
    roles = {(a.role, a.name) for a in m.authors}
    assert ("writer", "Ohba") in roles
    assert ("penciller", "Obata") in roles


def test_authors_dedup_within_role() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", authors=[MetadataAuthor(role="writer", name="Ohba")]),
        _rec("anilist", authors=[MetadataAuthor(role="writer", name="Ohba")], confidence=0.9),
    ])
    writers = [a for a in m.authors if a.role == "writer"]
    assert len(writers) == 1
    assert writers[0].name == "Ohba"


def test_writer_role_prefers_anilist_when_present() -> None:
    """AniList is authoritative for writer/cover_artist per the plan."""
    m = MetadataMerger().merge([
        _rec("mangadex", authors=[MetadataAuthor(role="writer", name="Wrong Name")]),
        _rec("anilist", authors=[MetadataAuthor(role="writer", name="Right Name")], confidence=0.9),
    ])
    writer = next(a for a in m.authors if a.role == "writer")
    assert writer.name == "Right Name"
    # And the provider attribute on the author points to anilist.
    assert writer.provider == "anilist"


def test_letterer_role_prefers_mangadex() -> None:
    m = MetadataMerger().merge([
        _rec("anilist", authors=[MetadataAuthor(role="letterer", name="A Letterer")], confidence=0.9),
        _rec("mangadex", authors=[MetadataAuthor(role="letterer", name="M Letterer")]),
    ])
    letterer = next(a for a in m.authors if a.role == "letterer")
    assert letterer.name == "M Letterer"
    assert letterer.provider == "mangadex"


# ------------------------------------------------------------- genres/tags


def test_genres_are_unioned() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", genres=["Action", "Mystery"]),
        _rec("anilist", genres=["Action", "Drama"], confidence=0.9),
    ])
    # Union, preserving first-seen order. Mangadex is first in
    # confidence-sorted order, then anilist contributes "Drama".
    assert "Action" in m.genres
    assert "Mystery" in m.genres
    assert "Drama" in m.genres
    assert len(m.genres) == 3


def test_tags_are_unioned() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", tags=["On Hiatus"]),
        _rec("anilist", tags=["Award Winning"], confidence=0.9),
    ])
    assert "On Hiatus" in m.tags
    assert "Award Winning" in m.tags


# ------------------------------------------------------------- alt titles


def test_alt_titles_exclude_main_title() -> None:
    m = MetadataMerger().merge([
        _rec("anilist", title="Naruto", alt_titles=["NARUTO", "ナルト", "Naruto"], confidence=0.9),
    ])
    # Case-insensitive: NARUTO, Naruto both match the main title and are
    # excluded; only the distinct alt survives.
    assert "ナルト" in m.alt_titles
    assert "Naruto" not in m.alt_titles
    assert "NARUTO" not in m.alt_titles


def test_alt_titles_deduped_across_providers() -> None:
    m = MetadataMerger().merge([
        _rec("anilist", title="X", alt_titles=["alt-1", "alt-2"], confidence=0.9),
        _rec("mangadex", title="X", alt_titles=["alt-1", "alt-3"]),
    ])
    # `alt-1` only appears once; both alt-2 and alt-3 are kept.
    assert m.alt_titles.count("alt-1") == 1
    assert "alt-2" in m.alt_titles
    assert "alt-3" in m.alt_titles


# --------------------------------------------------------- confidence


def test_confidence_is_weighted_average() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", confidence=0.5),
        _rec("anilist", confidence=0.9),
    ])
    # weighted = (0.5*0.5 + 0.9*0.9) / (0.5 + 0.9) = 1.06 / 1.4 = 0.757
    assert 0.7 < m.confidence < 0.8


# ------------------------------------------------------------ attribution


def test_attribution_is_populated() -> None:
    m = MetadataMerger().merge([
        _rec("mangadex", title="X", year=2000, cover_url="https://m/x.jpg"),
        _rec("anilist", title="Y", year=2001, cover_url="https://a/y.jpg", confidence=0.9),
    ])
    assert "title" in m.attribution
    assert "year" in m.attribution
    assert "cover_url" in m.attribution
    # All attributions point to a real provider name.
    for v in m.attribution.values():
        assert v in ("mangadex", "anilist", "google_books")


# ------------------------------------------------------------ to_dict


def test_to_dict_round_trip() -> None:
    m = MetadataMerger().merge([
        _rec("anilist", title="X", confidence=0.9),
    ])
    d = m.to_dict()
    assert d["title"] == "X"
    assert d["confidence"] > 0
    assert "anilist" in d["sources"]
