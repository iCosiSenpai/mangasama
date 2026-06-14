"""Async rate limiter wrapping aiolimiter.

A per-(scraper, domain) token bucket. Each call to `acquire()` waits
until a token is available, then returns. The bucket has a max rate
(default 30 req/min, configurable per scraper in `config/default.yaml`).

The async version is `AsyncLimiter(max_rate, time_period)` where
`time_period` is in seconds — so `AsyncLimiter(30, 60)` = 30 / minute.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from aiolimiter import AsyncLimiter

logger = structlog.get_logger("mangasama.core.rate_limiter")


class RateLimiter:
    """Per-key rate limiter.

    Keyed by `(scraper_name, domain)` so different scrapers and different
    domains don't share budgets. Concurrency cap: at most N in-flight
    requests per key (default 4).
    """

    def __init__(self, default_rpm: int = 30, default_concurrency: int = 4):
        self.default_rpm = default_rpm
        self.default_concurrency = default_concurrency
        self._buckets: dict[tuple[str, str], AsyncLimiter] = {}
        self._semaphores: dict[tuple[str, str], asyncio.Semaphore] = {}
        self._lock = asyncio.Lock()

    def bucket(self, scraper: str, domain: str, *, rpm: int | None = None) -> AsyncLimiter:
        """Return the AsyncLimiter for this (scraper, domain) pair."""
        key = (scraper, domain)
        if key not in self._buckets:
            self._buckets[key] = AsyncLimiter(rpm or self.default_rpm, 60.0)
        return self._buckets[key]

    def semaphore(self, scraper: str, domain: str, *, n: int | None = None) -> asyncio.Semaphore:
        """Return the in-flight concurrency semaphore for this pair."""
        key = (scraper, domain)
        if key not in self._semaphores:
            self._semaphores[key] = asyncio.Semaphore(n or self.default_concurrency)
        return self._semaphores[key]

    @asynccontextmanager
    async def acquire(self, scraper: str, domain: str, *, rpm: int | None = None) -> AsyncIterator[None]:
        """Wait for a rate-limit token AND a concurrency slot, then yield."""
        b = self.bucket(scraper, domain, rpm=rpm)
        s = self.semaphore(scraper, domain)
        async with b, s:
            yield

    def reset(self) -> None:
        """Drop all buckets (test helper)."""
        self._buckets.clear()
        self._semaphores.clear()


# Module-level singleton. ScraperRegistry and Downloader share it.
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        from app.settings import get_settings
        s = get_settings()
        _rate_limiter = RateLimiter(
            default_rpm=s.default_rate_limit_rpm,
            default_concurrency=s.scraper_concurrency,
        )
    return _rate_limiter


def reset_for_tests() -> None:
    """Drop the singleton (test helper)."""
    global _rate_limiter
    _rate_limiter = None
