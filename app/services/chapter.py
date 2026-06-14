"""Chapter service — read + delete for the `chapters` + `pages` tables.

Italian-first ordering: `it` < `en` < everything else, then numeric `sort`.

The CBZ packager is wired in step 11; for now `download_chapter_file`
returns the existing `file_path` if any, else 404.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ChapterNotFoundDB
from app.models.orm import Chapter, Series, Volume


# ----------------------------------------------------------------- read


def _italian_first_order() -> case:
    """SQL `CASE` expression: it=0, en=1, everything else=2."""
    return case(
        (Chapter.language == "it", 0),
        (Chapter.language == "en", 1),
        else_=2,
    )


async def list_chapters(
    session: AsyncSession,
    *,
    series_id: int | None = None,
    language: str | None = None,
    downloaded: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Chapter]:
    stmt = select(Chapter).options(selectinload(Chapter.pages))
    if series_id is not None:
        # Restrict to chapters belonging to a series.
        stmt = stmt.join(Volume, Volume.id == Chapter.volume_id).where(
            Volume.series_id == series_id
        )
    if language is not None:
        stmt = stmt.where(Chapter.language == language)
    if downloaded is True:
        stmt = stmt.where(Chapter.file_path.is_not(None))
    elif downloaded is False:
        stmt = stmt.where(Chapter.file_path.is_(None))
    stmt = (
        stmt.order_by(_italian_first_order().asc(), Chapter.sort.asc())
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_chapter(
    session: AsyncSession, chapter_id: int,
) -> Chapter:
    stmt = (
        select(Chapter)
        .where(Chapter.id == chapter_id)
        .options(selectinload(Chapter.pages))
    )
    ch = (await session.execute(stmt)).scalar_one_or_none()
    if ch is None:
        raise ChapterNotFoundDB(f"chapter {chapter_id} not found")
    return ch


# ----------------------------------------------------------------- file


async def download_chapter_file(
    session: AsyncSession, chapter_id: int,
) -> tuple[Path, str]:
    """Return `(absolute_path, filename)` for a downloaded CBZ.

    Raises `ChapterNotFoundDB` if the chapter has no `file_path` set
    yet (i.e. it has never been downloaded).
    """
    ch = await get_chapter(session, chapter_id)
    if not ch.file_path:
        raise ChapterNotFoundDB(
            f"chapter {chapter_id} has no CBZ yet (download first)"
        )
    p = Path(ch.file_path)
    if not p.is_absolute():
        # Resolve relative paths against the data dir.
        from app.settings import get_settings
        p = get_settings().data_dir / p
    if not p.exists():
        raise ChapterNotFoundDB(f"chapter {chapter_id} file missing on disk: {p}")
    return p, p.name


# ----------------------------------------------------------------- delete


async def delete_chapter(
    session: AsyncSession, chapter_id: int,
) -> None:
    """Hard delete the chapter row + its pages. Unlink the CBZ file if present."""
    ch = await get_chapter(session, chapter_id)
    if ch.file_path:
        try:
            p = Path(ch.file_path)
            if not p.is_absolute():
                from app.settings import get_settings
                p = get_settings().data_dir / p
            if p.exists():
                p.unlink()
        except OSError:
            # Don't block the DB delete on filesystem errors.
            pass
    await session.delete(ch)
    await session.flush()


# ----------------------------------------------------------------- stub


async def redownload_chapter(
    session: AsyncSession, chapter_id: int,
) -> dict:
    """Enqueue a forced re-download (overwrite) of an existing chapter.

    Reconstructs a `ScrapedChapter` from the stored row and pushes a
    `DownloadTask(overwrite=True)` onto the download queue.
    """
    ch = (
        await session.execute(
            select(Chapter)
            .where(Chapter.id == chapter_id)
            .options(selectinload(Chapter.volume))
        )
    ).scalar_one_or_none()
    if ch is None:
        raise ChapterNotFoundDB(f"chapter {chapter_id} not found")

    from app.scrapers.base import ScrapedChapter
    from app.services.downloader import DownloadTask, enqueue_download

    scraped = ScrapedChapter(
        source=ch.source_provider,
        external_id=ch.source_id,
        url=ch.source_url or "",
        number=ch.number,
        title=ch.title,
        language=ch.language,
        volume_number=ch.volume.number if ch.volume else None,
    )
    enqueue_download(DownloadTask(
        series_id=ch.volume.series_id,
        provider=ch.source_provider,
        chapter=scraped,
        language=ch.language,
        overwrite=True,
    ))
    return {"scheduled": 1, "chapter_id": chapter_id}


# Export for tests / other services.
__all__ = [
    "list_chapters",
    "get_chapter",
    "delete_chapter",
    "download_chapter_file",
    "redownload_chapter",
    "_italian_first_order",  # noqa: SLF001 — used by tests
]
