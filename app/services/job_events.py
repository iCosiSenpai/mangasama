"""In-process pub/sub for job progress events (SSE backend).

The download workers (`app/services/downloader.py`) publish a small dict
on every `provider_jobs` state change; the SSE endpoint
(`GET /api/jobs/stream`) subscribes and forwards the events to the
browser. Everything runs in the app's single event loop, so a plain
`asyncio.Queue` fan-out is enough — no external broker.

Events are best-effort: if a subscriber's queue is full (a slow client)
the event is dropped for that subscriber rather than blocking the worker.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog

logger = structlog.get_logger("mangasama.services.job_events")

_MAX_SUBSCRIBER_BACKLOG = 100


class JobEventBus:
    """Fan-out of job events to any number of subscribers."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def publish(self, event: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer — drop this event for them, don't block.
                logger.warning("job_events.subscriber_backlog_full")

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_MAX_SUBSCRIBER_BACKLOG)
        self._subscribers.add(q)
        try:
            yield q
        finally:
            self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


_bus: JobEventBus | None = None


def get_job_event_bus() -> JobEventBus:
    global _bus
    if _bus is None:
        _bus = JobEventBus()
    return _bus


def publish_job(event: dict[str, Any]) -> None:
    """Best-effort publish helper used by the download workers."""
    get_job_event_bus().publish(event)


def reset_for_tests() -> None:
    global _bus
    _bus = None


__all__ = [
    "JobEventBus",
    "get_job_event_bus",
    "publish_job",
    "reset_for_tests",
]
