"""Metadata provider base classes and DTOs.

A metadata provider is a thin wrapper around an external service
(AniList, MangaDex metadata API, Google Books) that exposes
*enriched* series data — better titles, summaries, covers, author
roles, year, status, genres/tags — independent of where the
chapter bytes come from.

The orchestrator (step 8) wires this up: when the user adds a
series, we call one or more providers, merge their results with
`MetadataMerger`, and write the merged record into the `series`
row + `series_external_ids` rows.

The DTOs are deliberately separate from `app.scrapers.base` because
a scraper talks about "how do I get the chapter pages" and a
metadata provider talks about "who is the series, who wrote it,
what year did it start, what's the cover". They overlap on a
core "series" shape but differ in the fields they expose.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

#: A metadata record's confidence score. Range [0.0, 1.0].
Confidence = float

#: Provider identifiers — must match the `provider` column in
#: `series_external_ids` and the `name` class attribute on each
#: concrete provider.
ProviderName = Literal["anilist", "mangadex", "google_books"]


@dataclass
class MetadataCandidate:
    """A single search hit from a metadata provider."""

    provider: ProviderName
    external_id: str            # provider-specific ID
    url: str | None = None
    title: str = ""
    alt_titles: list[str] = field(default_factory=list)
    year: int | None = None
    cover_url: str | None = None
    # Free-form provider-specific score. For AniList this is the
    # search relevance (higher is better). For our consumer we treat
    # it as a hint, not a hard rank.
    score: float = 0.0
    # What languages the series has translations in (BCP-47 codes).
    # Used to pick the right metadata language and to warn the user
    # that a series has no Italian translation.
    available_languages: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetadataAuthor:
    """One credited person, with their role.

    Roles match the ComicInfo v2.1 schema (lowercase):
      writer, penciller, inker, colorist, letterer,
      cover_artist, editor, translator
    """

    role: str
    name: str


@dataclass
class MetadataRecord:
    """The full enriched record from one provider.

    Confidence is provider-internal (0..1) and is folded into the
    merger. The merger may also set `confidence` on the *merged*
    record it returns.
    """

    provider: ProviderName
    external_id: str
    url: str | None = None
    title: str = ""
    alt_titles: list[str] = field(default_factory=list)
    summary: str | None = None
    year: int | None = None
    status: str | None = None
    cover_url: str | None = None
    # Country of origin: "JP" / "KR" / "CN" / "TW" for our type mapping.
    country: str | None = None
    # Already-mapped type. Providers should do the JP→manga / KR→manhwa /
    # CN→manhua mapping themselves; the merger treats type as a
    # consensus vote.
    type: str | None = None  # manga | manhua | manhwa
    authors: list[MetadataAuthor] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    publisher: str | None = None
    available_languages: list[str] = field(default_factory=list)
    # Confidence this provider has in the record (provider-internal).
    confidence: Confidence = 0.8
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseMetadataProvider(ABC):
    """Contract every metadata provider implements."""

    name: ProviderName = ""           # type: ignore[assignment]
    rate_limit_rpm: int = 30

    def __init__(self, http: Any = None):
        if http is None:
            from app.core.http_client import get_http
            http = get_http()
        self.http = http

    @abstractmethod
    async def health_check(self) -> bool: ...

    @abstractmethod
    async def search(
        self, query: str, *, limit: int = 10, language: str | None = None,
    ) -> list[MetadataCandidate]: ...

    @abstractmethod
    async def get_record(self, external_id: str) -> MetadataRecord: ...

    async def get_cover(self, external_id: str) -> bytes | None:
        """Download the cover image bytes (optional, default = None).

        Providers that don't support direct cover download (e.g. AniList
        returns only the URL) should leave this at the default; the
        merger + cover_cache will fetch via `cover_url` instead.
        """
        return None
