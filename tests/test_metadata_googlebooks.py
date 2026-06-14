"""Google Books provider tests (dormant in v1)."""

from __future__ import annotations

import pytest

from app.metadata.googlebooks import GoogleBooksProvider


@pytest.fixture
def provider() -> GoogleBooksProvider:
    return GoogleBooksProvider()


@pytest.mark.asyncio
async def test_health_check_false_when_disabled(provider: GoogleBooksProvider) -> None:
    # google_books_enabled defaults to False in settings.
    assert await provider.health_check() is False


@pytest.mark.asyncio
async def test_search_returns_empty_when_disabled(provider: GoogleBooksProvider) -> None:
    assert await provider.search("lord of the rings") == []


@pytest.mark.asyncio
async def test_get_record_raises_not_implemented(provider: GoogleBooksProvider) -> None:
    with pytest.raises(NotImplementedError):
        await provider.get_record("abc")
