"""Domain exceptions for MangaSama.

The HTTP boundary converts these to JSON error responses; the scheduler
and downloader catch them to decide retry vs. fallback-to-next-source.
"""

from __future__ import annotations


class MangaSamaError(Exception):
    """Base for all MangaSama-specific errors."""


# --- Scraping --------------------------------------------------------------


class ScraperError(MangaSamaError):
    """Base for scraper errors."""


class SourceUnavailable(ScraperError):
    """The source is reachable but failing consistently (5xx, timeouts).

    The orchestrator should try the next source in `source_priority`.
    """

    def __init__(self, message: str, *, source: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.source = source
        self.status_code = status_code


class BlockedByCloudflare(ScraperError):
    """The site returned a Cloudflare challenge (403/503 with `server: cloudflare`).

    The orchestrator should either:
      - Try the next source in `source_priority`, OR
      - If `CLOUDFLARE_SOLVER` is set, dispatch to Playwright/FlareSolverr
        and retry the same source.
    """

    def __init__(self, message: str, *, source: str | None = None, url: str | None = None):
        super().__init__(message)
        self.source = source
        self.url = url


class ChapterNotFound(ScraperError):
    """The chapter exists on the source side but the scraper can't find it."""


class SeriesNotFound(ScraperError):
    """The series URL/ID is unknown to the source."""


class RateLimited(ScraperError):
    """The source returned 429. Caller should slow down."""

    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


# --- Packager / DB ---------------------------------------------------------


class PackageError(MangaSamaError):
    """CBZ packaging failed."""


class InvalidComicInfo(PackageError):
    """ComicInfo.xml generation produced invalid data."""


# --- Queue / capacity ------------------------------------------------------


class DownloadQueueFull(MangaSamaError):
    """The in-process download queue is at capacity (→ HTTP 503).

    Callers should retry later; the workers are draining the backlog.
    """


# --- Config / settings -----------------------------------------------------


class ConfigError(MangaSamaError):
    """User configuration is invalid or missing."""


class UnknownScraper(ConfigError, KeyError):
    """A scraper name has no registered implementation (→ HTTP 400).

    Subclasses both `ConfigError` (so the HTTP boundary maps it to 400) and
    `KeyError` (so existing ``except KeyError`` call sites keep working).
    """


class LibraryNotFound(MangaSamaError, KeyError):
    """Library ID does not exist (or is soft-deleted)."""


class SeriesNotFoundDB(MangaSamaError, KeyError):
    """Series ID does not exist (or is soft-deleted) in the DB layer."""


class ChapterNotFoundDB(MangaSamaError, KeyError):
    """Chapter ID does not exist in the DB layer, or has no `file_path` yet."""


class JobNotFound(MangaSamaError, KeyError):
    """Job ID does not exist in `provider_jobs`."""


class CoverNotFound(MangaSamaError, KeyError):
    """Series has no cover, or the cached cover file is missing."""
