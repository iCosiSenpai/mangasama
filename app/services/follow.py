"""Follow orchestration — list a series' chapters and enqueue the new ones.

`check_series` is the per-series unit the (future) APScheduler cron will
call; `backfill_series` is the on-demand variant that ignores the "due"
window. Both resolve a provider, list chapters Italian-first, diff
against what's already in the DB, and enqueue the missing chapters onto
the download queue.

The actual page download + CBZ packaging happens in
`app/services/downloader.py`; this module never touches disk.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConfigError, SeriesNotFoundDB
from app.models.orm import Chapter, FollowLog, Library, Series, Volume
from app.scrapers.base import BaseScraper, ScrapedChapter
from app.scrapers.registry import get_scraper
from app.scrapers.source_policy import is_scraper_available
from app.services.downloader import DownloadTask, _to_sort, enqueue_download
from app.services.language_picker import select_chapters

logger = structlog.get_logger("mangasama.services.follow")


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _load_series(session: AsyncSession, series_id: int) -> Series:
    s = (
        await session.execute(
            select(Series)
            .where(Series.id == series_id, Series.deleted.is_(False))
            .options(selectinload(Series.external_ids), selectinload(Series.library))
        )
    ).scalar_one_or_none()
    if s is None:
        raise SeriesNotFoundDB(f"series {series_id} not found")
    return s


def _pick_provider(series: Series) -> tuple[str, str]:
    """Return `(provider_name, external_id)` for the first usable provider.

    Walks `series.source_priority` (falling back to `library.providers`)
    and returns the first one that (a) has an external id mapped on the
    series and (b) is a registered scraper. Raises `ConfigError` (→ HTTP 400)
    if none — e.g. a series with no external id mapped to any known provider.
    """
    by_provider = {eid.provider: eid.external_id for eid in (series.external_ids or [])}
    order = list(series.source_priority or []) or list(series.library.providers or [])
    for name in order:
        if name in by_provider and is_scraper_available(name):
            return name, by_provider[name]
    raise ConfigError(
        f"series {series.id} has no usable provider (mapped: {sorted(by_provider)})"
    )


async def _existing_keys(
    session: AsyncSession, series_id: int, provider: str,
) -> set[tuple[str, str]]:
    """`{(source_id, language)}` already present for this series+provider."""
    rows = (
        await session.execute(
            select(Chapter.source_id, Chapter.language)
            .join(Volume, Volume.id == Chapter.volume_id)
            .where(Volume.series_id == series_id, Chapter.source_provider == provider)
        )
    ).all()
    return {(sid, lang) for sid, lang in rows}


async def _list_selected(
    series: Series, scraper: BaseScraper, external_id: str,
    *, language_priority: list[str] | None = None,
) -> list[ScrapedChapter]:
    chapters = await scraper.get_chapters(external_id)
    languages = ["it", "en"] if series.library.italian_priority else None
    selected = select_chapters(
        chapters, language_priority=language_priority, languages=languages,
    )
    # Sources list a chapter once per language and once per scanlation
    # group, so the same chapter `number` shows up multiple times. Keep
    # exactly ONE entry per number: `select_chapters` already ordered the
    # list Italian-first, so the first occurrence is the preferred
    # language/upload (this is the italian-first invariant in action).
    seen_numbers: set[str] = set()
    deduped: list[ScrapedChapter] = []
    for c in selected:
        if c.number in seen_numbers:
            continue
        seen_numbers.add(c.number)
        deduped.append(c)
    return deduped


async def check_series(session: AsyncSession, series_id: int) -> dict:
    """List a series' chapters and enqueue the ones we don't have yet.

    Always writes a `FollowLog` row and updates `series.last_checked_at`.
    """
    started = time.perf_counter()
    series = await _load_series(session, series_id)
    enqueued = 0
    status = "ok"
    error: str | None = None
    try:
        provider, ext = _pick_provider(series)
        scraper = get_scraper(provider)
        selected = await _list_selected(series, scraper, ext)
        existing = await _existing_keys(session, series_id, provider)
        for ch in selected:
            if (ch.external_id, ch.language) in existing:
                continue
            enqueue_download(DownloadTask(
                series_id=series_id, provider=provider,
                chapter=ch, language=ch.language,
            ))
            enqueued += 1
    except Exception as e:
        status = "error"
        error = str(e)
        logger.warning("follow.check_failed", series_id=series_id, error=error)

    session.add(FollowLog(
        series_id=series_id,
        new_chapters_count=enqueued,
        status=status,
        error=error,
        duration_ms=int((time.perf_counter() - started) * 1000),
    ))
    series.last_checked_at = _utcnow()
    return {"checked": series_id, "enqueued": enqueued, "status": status}


async def backfill_series(
    session: AsyncSession,
    series_id: int,
    *,
    count: int | None = None,
    language_priority: list[str] | None = None,
) -> dict:
    """Enqueue the (latest `count`) missing chapters, ignoring the due window."""
    series = await _load_series(session, series_id)
    provider, ext = _pick_provider(series)
    scraper = get_scraper(provider)
    selected = await _list_selected(
        series, scraper, ext, language_priority=language_priority,
    )
    existing = await _existing_keys(session, series_id, provider)
    missing = [c for c in selected if (c.external_id, c.language) not in existing]
    if count is not None and count > 0:
        missing = sorted(missing, key=lambda c: _to_sort(c.number), reverse=True)[:count]
    for ch in missing:
        enqueue_download(DownloadTask(
            series_id=series_id, provider=provider, chapter=ch, language=ch.language,
        ))
    return {"scheduled": len(missing), "series_id": series_id}


async def list_followed_status(
    session: AsyncSession,
) -> list[tuple[Series, FollowLog | None]]:
    """Return each followed series paired with its most recent `FollowLog`."""
    series_rows = (
        await session.execute(
            select(Series)
            .where(Series.followed.is_(True), Series.deleted.is_(False))
            .order_by(Series.sort_title.asc().nullslast(), Series.id.asc())
        )
    ).scalars().all()
    out: list[tuple[Series, FollowLog | None]] = []
    for s in series_rows:
        log = (
            await session.execute(
                select(FollowLog)
                .where(FollowLog.series_id == s.id)
                .order_by(FollowLog.checked_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        out.append((s, log))
    return out


async def check_due_series(session: AsyncSession) -> dict:
    """Run `check_series` for every followed series past its check interval.

    Implemented now and unit-testable; the periodic APScheduler trigger
    that calls it is wired in a later round.
    """
    now = _utcnow()
    rows = (
        await session.execute(
            select(Series, Library)
            .join(Library, Library.id == Series.library_id)
            .where(Series.followed.is_(True), Series.deleted.is_(False))
        )
    ).all()
    due_ids: list[int] = []
    for series, library in rows:
        if series.last_checked_at is None:
            due_ids.append(series.id)
            continue
        interval = timedelta(hours=library.follow_interval_hours or 24)
        last = series.last_checked_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if last + interval <= now:
            due_ids.append(series.id)

    for sid in due_ids:
        await check_series(session, sid)
    return {"due": len(due_ids), "series_ids": due_ids}


__all__ = [
    "backfill_series",
    "check_due_series",
    "check_series",
    "list_followed_status",
]
