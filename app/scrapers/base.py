"""Scraper base classes and DTOs.

Every concrete scraper (MangaDex, MangaEden, MangaWorld, …) implements
`BaseScraper`. The contract returns plain dataclasses — not ORM models —
so the orchestration layer is fully decoupled from the DB and from any
one provider's data shape.

The 3 dataclasses:
  - `ScrapedSeries`  — what we know about a series (title, authors, cover, ...)
  - `ScrapedChapter` — one chapter from a series (number, language, url, ...)
  - `ScrapedPage`    — one page of a chapter (url only, never bytes)

Bytes come from `HttpClient.get_bytes`/`get_stream` directly in the
downloader (`app/services/downloader.py`), not from the scraper.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from app.core.exceptions import (
    ChapterNotFound,
    SeriesNotFound,
    SourceUnavailable,
)

ContentType = Literal["manga", "manhua", "manhwa"]

__all__ = [
    "ContentType",
    "ScrapedSeries",
    "ScrapedChapter",
    "ScrapedPage",
    "BaseScraper",
    "SeriesNotFound",
    "ChapterNotFound",
    "SourceUnavailable",
]


@dataclass
class ScrapedSeries:
    """A series returned by a scraper."""

    source: str
    external_id: str
    url: str
    title: str
    alt_titles: list[str] = field(default_factory=list)
    summary: str | None = None
    year: int | None = None
    status: str | None = None  # ongoing|completed|hiatus|cancelled|unknown
    cover_url: str | None = None
    authors: list[tuple[str, str]] = field(default_factory=list)  # (role, name)
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    type: ContentType = "manga"
    # Free-form provider-specific data (e.g. MangaDex `lastChapter`, `lastVolume`).
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScrapedChapter:
    """A chapter of a series, as returned by the scraper."""

    source: str
    external_id: str
    url: str
    number: str
    title: str | None = None
    language: str = "en"  # BCP-47
    volume_number: str | None = None
    pages_count: int | None = None
    published_at: datetime | None = None
    scanlation_group: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScrapedPage:
    """A page of a chapter. The scraper never returns bytes — only URLs."""

    index: int
    url: str
    width: int | None = None
    height: int | None = None


class BaseScraper(ABC):
    """The contract every scraper must implement.

    Subclasses are expected to be *stateless* w.r.t. the DB. The DB-aware
    `ScraperRegistry` and orchestrator own the persistence concerns.
    """

    # ---- class-level metadata (set by subclasses) -----------------------
    name: str = ""                  # unique slug, e.g. "mangadex"
    display_name: str = ""          # human-friendly, e.g. "MangaDex"
    base_url: str = ""              # canonical API/HTML root
    supported_languages: list[str] = ["en", "it"]
    rate_limit_rpm: int = 30
    requires_browser: bool = False  # Playwright/FlareSolverr

    def __init__(self, http: Any = None):
        # The HttpClient is injected so we can swap it in tests.
        # We import lazily to avoid a circular import at module load.
        if http is None:
            from app.core.http_client import get_http
            http = get_http()
        self.http = http

    # ---- lifecycle -------------------------------------------------------

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the source is reachable and responding as expected.

        Used by the cron in `app/services/health.py`. Should be cheap
        (one GET, no big payloads) and quick (timeout < 10s).
        """

    @abstractmethod
    async def search(
        self, query: str, *, limit: int = 20, language: str | None = None
    ) -> list[ScrapedSeries]:
        """Return a list of series matching `query`.

        `language` is a hint: e.g. prefer titles that exist in that
        translation, or just filter candidates. Scrapers that don't
        support language-aware search can ignore the param.
        """

    @abstractmethod
    async def get_series(self, url_or_id: str) -> ScrapedSeries:
        """Fetch full details for a single series (cover URL, authors, ...)."""

    @abstractmethod
    async def get_chapters(
        self,
        external_id: str,
        *,
        language: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[ScrapedChapter]:
        """Return chapters of a series, oldest first by default.

        `language` filters by translation; None = no filter (caller picks).
        Pagination via `limit`/`offset`.
        """

    @abstractmethod
    async def get_pages(self, chapter_external_id: str) -> list[ScrapedPage]:
        """Return the page URLs of a chapter.

        The downloader (step 11) is responsible for actually fetching the
        bytes. We keep the scraper free of I/O on the page payload because
        pages are large and we want a thin, fast abstraction.
        """

    # ---- helpers ---------------------------------------------------------

    def _domain(self) -> str:
        """Extract the registrable domain for the rate-limiter bucket."""
        from urllib.parse import urlparse
        host = urlparse(self.base_url).hostname or ""
        return host.lstrip("www.") or self.base_url
