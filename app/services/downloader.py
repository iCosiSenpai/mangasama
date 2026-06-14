"""Download engine — turns a `ScrapedChapter` into a CBZ on disk.

This is the core of step 11. The design separates two concerns:

  - `download_chapter()` — the pure, idempotent coroutine that does the
    real work (fetch pages → pack CBZ → persist Volume/Chapter/Page). It
    is fully testable on its own, no queue required.
  - `DownloadQueue` + workers — an in-process `asyncio.Queue` consumed by
    N workers, each opening its own DB session. `start_download_workers`
    / `stop_download_workers` are called from the FastAPI lifespan.

Idempotency key: `(source_provider, source_id, language)` — a chapter
downloaded twice is the same `chapters` row (enforced by a DB unique
constraint and pre-checked here).

The APScheduler wiring (periodic follow checks) lives in a later round;
this module only provides the engine + queue.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.hashing import sha256_bytes
from app.core.http_client import get_http
from app.models.orm import Chapter, Library, Page, ProviderJob, Series, Volume
from app.scrapers.base import BaseScraper, ScrapedChapter
from app.scrapers.registry import get_scraper
from app.services import folder_strategy as fs
from app.services.cbz import CbzPackager, PageBlob
from app.services.comicinfo import ComicInfo, ComicPageInfo, story_arc_number
from app.settings import get_settings

logger = structlog.get_logger("mangasama.services.downloader")


# ----------------------------------------------------------------- task DTO


@dataclass
class DownloadTask:
    """One unit of work for the download queue."""

    series_id: int
    provider: str
    chapter: ScrapedChapter
    language: str
    overwrite: bool = False


# ----------------------------------------------------------------- helpers


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _to_sort(num: str | None) -> float:
    """Parse a chapter/volume number to a sortable float. `'1.5'`->1.5,
    non-numeric or empty -> 0.0."""
    s = (num or "").strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        # Strip a leading non-numeric prefix (e.g. "S1" -> 1).
        digits = "".join(c for c in s if (c.isdigit() or c == "."))
        try:
            return float(digits) if digits else 0.0
        except ValueError:
            return 0.0


async def _get_or_create_volume(
    session: AsyncSession, series_id: int, number: str | None, language: str,
) -> Volume:
    num = (number or "1").strip() or "1"
    stmt = select(Volume).where(
        Volume.series_id == series_id,
        Volume.number == num,
        Volume.language == language,
    )
    vol = (await session.execute(stmt)).scalar_one_or_none()
    if vol is None:
        vol = Volume(series_id=series_id, number=num, sort=_to_sort(num), language=language)
        session.add(vol)
        await session.flush()
    return vol


def _build_comic_info(series: Series, scraped: ScrapedChapter, library: Library) -> ComicInfo:
    """Map series + scraped chapter to a ComicInfo v2.1 record."""
    authors: dict[str, list[str]] = {}
    for a in series.authors or []:
        authors.setdefault((a.role or "").lower(), []).append(a.name)
    # manhua reads left-to-right; manga/manhwa right-to-left.
    rtl = (library.type or "manga") != "manhua"
    return ComicInfo(
        title=scraped.title or "",
        series=series.title,
        number=scraped.number,
        volume=scraped.volume_number,
        summary=series.summary,
        language_iso=scraped.language,
        web=scraped.url or None,
        manga=True,
        right_to_left=rtl,
        authors=authors,
        genres=[g.genre for g in (series.genres or [])],
        tags=[t.tag for t in (series.tags or [])],
        translator=scraped.scanlation_group,
        story_arc=series.title,
        story_arc_number=story_arc_number(scraped.volume_number, scraped.number),
    )


# ----------------------------------------------------------------- core


async def download_chapter(
    session: AsyncSession,
    *,
    series: Series,
    scraped: ScrapedChapter,
    scraper: BaseScraper,
    library: Library,
    overwrite: bool = False,
) -> Chapter | None:
    """Download one chapter and pack it into a CBZ.

    Idempotent: if the chapter already exists with a CBZ on disk and
    `overwrite` is False, returns the existing row without re-fetching.
    Returns the persisted `Chapter`, or `None` if the source yielded no
    pages.
    """
    # 1. Idempotency.
    existing = (
        await session.execute(
            select(Chapter)
            .where(
                Chapter.source_provider == scraper.name,
                Chapter.source_id == scraped.external_id,
                Chapter.language == scraped.language,
            )
            .options(selectinload(Chapter.pages))
        )
    ).scalar_one_or_none()
    if (
        existing is not None
        and existing.file_path
        and not overwrite
        and Path(existing.file_path).exists()
    ):
        logger.info(
            "download.skip_existing",
            provider=scraper.name, source_id=scraped.external_id,
            language=scraped.language,
        )
        return existing

    # 2. Page URLs. (No DB writes happen until everything is fetched +
    #    packed, so a concurrent worker isn't blocked on a write lock held
    #    for the whole network download.)
    scraped_pages = await scraper.get_pages(scraped.external_id)
    if not scraped_pages:
        logger.warning(
            "download.no_pages",
            provider=scraper.name, source_id=scraped.external_id,
        )
        return None

    # 4. Fetch bytes.
    http = get_http()
    blobs: list[PageBlob] = []
    raw_by_index: dict[int, bytes] = {}
    for sp in scraped_pages:
        domain = urlparse(sp.url).hostname or scraper.base_url
        raw = await http.get_bytes(
            sp.url, scraper=scraper.name, domain=domain, rpm=scraper.rate_limit_rpm,
        )
        raw_by_index[sp.index] = raw
        blobs.append(PageBlob(bytes=raw, index=sp.index, width=sp.width, height=sp.height))
    blobs.sort(key=lambda b: b.index)

    # 5. ComicInfo + 6. destination path.
    comic_info = _build_comic_info(series, scraped, library)
    comic_info = ComicInfo(
        **{**comic_info.__dict__, "pages": [
            ComicPageInfo(index=b.index, width=b.width, height=b.height) for b in blobs
        ]}
    )
    chapter_path = fs.resolve_path(
        library.folder_strategy,
        Path(library.root_path),
        fs.SeriesVolumeChapter(
            series_title=series.title,
            chapter_number=scraped.number,
            chapter_title=scraped.title,
            language=scraped.language,
            volume_number=scraped.volume_number,
        ),
    )

    # 7. Pack.
    result = CbzPackager().build(blobs, comic_info, chapter_path.path)

    # 8. Persist: volume + chapter + pages (the only DB writes — kept after
    #    the network fetch so the write transaction is short-lived).
    volume = await _get_or_create_volume(
        session, series.id, scraped.volume_number, scraped.language,
    )
    url_by_index = {sp.index: sp.url for sp in scraped_pages}
    pad = max(3, len(str(len(blobs))))
    new_pages = [
        Page(
            index=b.index,
            filename=f"page{b.index + 1:0{pad}d}.jpg",
            source_url=url_by_index.get(b.index),
            width=b.width,
            height=b.height,
            sha256=sha256_bytes(raw_by_index[b.index]),
        )
        for b in blobs
    ]

    ch = existing
    if ch is None:
        ch = Chapter(
            volume_id=volume.id,
            source_provider=scraper.name,
            source_id=scraped.external_id,
            language=scraped.language,
        )
        # Assign pages while the row is still pending → no lazy load.
        ch.pages = new_pages
        session.add(ch)
    else:
        # Overwrite: drop the old page rows *and flush* before inserting
        # the new ones, otherwise the INSERTs would collide with the old
        # rows on the (chapter_id, index) unique constraint.
        ch.pages.clear()
        await session.flush()
        ch.pages = new_pages
    ch.volume_id = volume.id
    ch.number = scraped.number
    ch.sort = _to_sort(scraped.number)
    ch.title = scraped.title
    ch.source_url = scraped.url or None
    ch.pages_count = result.page_count
    ch.file_path = str(result.path)
    ch.cbz_size = result.size_bytes
    ch.cbz_sha256 = result.sha256
    ch.downloaded_at = _utcnow()
    await session.flush()
    logger.info(
        "download.ok",
        provider=scraper.name, source_id=scraped.external_id,
        language=scraped.language, pages=result.page_count, path=str(result.path),
    )
    return ch


# ----------------------------------------------------------------- queue


class DownloadQueue:
    """In-process queue + worker pool for chapter downloads."""

    def __init__(self) -> None:
        settings = get_settings()
        self._queue: asyncio.Queue[DownloadTask] = asyncio.Queue(
            maxsize=settings.download_queue_size,
        )
        self._workers: list[asyncio.Task] = []

    def enqueue(self, task: DownloadTask) -> None:
        self._queue.put_nowait(task)

    def pending(self) -> int:
        return self._queue.qsize()

    async def _run_task(self, task: DownloadTask) -> None:
        """Process one task using *short* DB transactions.

        The job row is created and committed in its own transaction, the
        network download + CBZ packing run with no open write transaction,
        and the result is persisted/marked in a final short transaction.
        This keeps SQLite write locks brief so concurrent workers don't
        time out against each other.
        """
        job_id = await self._create_job(task)
        self._publish(job_id, task, "running", 0)
        try:
            from app.db.session import session_scope

            async with session_scope() as session:
                series = (
                    await session.execute(
                        select(Series)
                        .where(Series.id == task.series_id)
                        .options(
                            selectinload(Series.authors),
                            selectinload(Series.genres),
                            selectinload(Series.tags),
                            selectinload(Series.library),
                        )
                    )
                ).scalar_one_or_none()
                if series is None:
                    raise ValueError(f"series {task.series_id} not found")
                scraper = get_scraper(task.provider)
                await download_chapter(
                    session,
                    series=series,
                    scraped=task.chapter,
                    scraper=scraper,
                    library=series.library,
                    overwrite=task.overwrite,
                )
            await self._set_job(job_id, "done", progress=100)
            self._publish(job_id, task, "done", 100)
        except Exception as e:
            logger.error(
                "download.job_failed",
                provider=task.provider, source_id=task.chapter.external_id,
                error=str(e),
            )
            await self._set_job(job_id, "error", error=str(e))
            self._publish(job_id, task, "error", 0, str(e))

    @staticmethod
    async def _create_job(task: DownloadTask) -> int:
        from app.db.session import session_scope

        async with session_scope() as session:
            job = ProviderJob(
                job_type="download",
                provider=task.provider,
                payload={
                    "series_id": task.series_id,
                    "provider": task.provider,
                    "source_id": task.chapter.external_id,
                    "language": task.language,
                },
                status="running",
                started_at=_utcnow(),
            )
            session.add(job)
            await session.flush()
            return job.id

    @staticmethod
    async def _set_job(
        job_id: int, status: str, *, progress: int = 0, error: str | None = None,
    ) -> None:
        from app.db.session import session_scope

        async with session_scope() as session:
            job = await session.get(ProviderJob, job_id)
            if job is None:
                return
            job.status = status
            job.progress = progress
            job.error = error
            job.finished_at = _utcnow()

    @staticmethod
    def _publish(
        job_id: int, task: DownloadTask, status: str, progress: int,
        error: str | None = None,
    ) -> None:
        from app.services.job_events import publish_job

        publish_job({
            "id": job_id,
            "job_type": "download",
            "provider": task.provider,
            "status": status,
            "progress": progress,
            "error": error,
            "series_id": task.series_id,
            "source_id": task.chapter.external_id,
            "language": task.language,
        })

    async def _worker_loop(self) -> None:
        while True:
            task = await self._queue.get()
            try:
                await self._run_task(task)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # a task must never kill its worker
                logger.error(
                    "download.worker_task_crashed",
                    provider=task.provider, source_id=task.chapter.external_id,
                    error=str(e),
                )
            finally:
                self._queue.task_done()

    def start(self, count: int) -> None:
        if self._workers:
            return
        for _ in range(max(1, count)):
            self._workers.append(asyncio.create_task(self._worker_loop()))
        logger.info("download.workers_started", count=len(self._workers))

    async def stop(self) -> None:
        for w in self._workers:
            w.cancel()
        for w in self._workers:
            with contextlib.suppress(asyncio.CancelledError):
                await w
        self._workers.clear()
        logger.info("download.workers_stopped")


# Module-level singleton.
_queue: DownloadQueue | None = None


def get_download_queue() -> DownloadQueue:
    global _queue
    if _queue is None:
        _queue = DownloadQueue()
    return _queue


def enqueue_download(task: DownloadTask) -> None:
    """Public helper used by the follow scheduler + backfill."""
    get_download_queue().enqueue(task)


async def start_download_workers() -> None:
    """Called from the FastAPI lifespan."""
    settings = get_settings()
    get_download_queue().start(settings.download_worker_count)


async def stop_download_workers() -> None:
    global _queue
    if _queue is not None:
        await _queue.stop()
        _queue = None


def reset_for_tests() -> None:
    """Drop the queue singleton (test helper)."""
    global _queue
    _queue = None


__all__ = [
    "DownloadQueue",
    "DownloadTask",
    "download_chapter",
    "enqueue_download",
    "get_download_queue",
    "reset_for_tests",
    "start_download_workers",
    "stop_download_workers",
]
