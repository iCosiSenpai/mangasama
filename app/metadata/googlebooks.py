"""Google Books metadata provider — dormant in v1.

The infrastructure is here so a future "novel" library type can flip
`google_books_enabled=True` and get ISBN / publisher / page-count
metadata without further work.

In v1, the provider's `health_check` always returns False and
`search` / `get_record` raise `NotImplementedError`. The metadata
registry filters it out via `enabled = settings.google_books_enabled`.
"""

from __future__ import annotations

import structlog

from app.metadata.base import (
    BaseMetadataProvider,
    MetadataCandidate,
    MetadataRecord,
)

logger = structlog.get_logger("mangasama.metadata.googlebooks")


class GoogleBooksProvider(BaseMetadataProvider):
    name = "google_books"  # type: ignore[assignment]
    rate_limit_rpm = 30

    async def health_check(self) -> bool:
        from app.settings import get_settings
        if not get_settings().google_books_enabled:
            logger.debug("google_books.disabled")
            return False
        # Future: a /volumes?q=* probe. Not implemented in v1.
        return False

    async def search(
        self, query: str, *, limit: int = 10, language: str | None = None,
    ) -> list[MetadataCandidate]:
        from app.settings import get_settings
        if not get_settings().google_books_enabled:
            return []
        raise NotImplementedError("Google Books metadata: not implemented in v1")

    async def get_record(self, external_id: str) -> MetadataRecord:
        from app.settings import get_settings
        if not get_settings().google_books_enabled:
            raise NotImplementedError("Google Books metadata: not implemented in v1")
        raise NotImplementedError("Google Books metadata: not implemented in v1")
