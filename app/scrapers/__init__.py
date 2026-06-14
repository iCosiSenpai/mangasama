"""scrapers package init."""

from app.scrapers.base import (
    BaseScraper,
    ContentType,
    ScrapedChapter,
    ScrapedPage,
    ScrapedSeries,
)
from app.scrapers.registry import (
    ScraperRegistry,
    get_scraper,
    get_scraper_registry,
    reset_for_tests,
)

__all__ = [
    "BaseScraper",
    "ContentType",
    "ScrapedChapter",
    "ScrapedPage",
    "ScrapedSeries",
    "ScraperRegistry",
    "get_scraper",
    "get_scraper_registry",
    "reset_for_tests",
]
