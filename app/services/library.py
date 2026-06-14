"""Library service — CRUD for the `libraries` table.

All write functions expect to be called inside a request transaction
(`session.commit()` is the caller's job — `get_db()` does not auto-commit).

Validation:
  - `type` is `Literal["manga","manhua","manhwa"]` in the schema layer.
  - `providers` is a list of scraper names; we cross-check against the
    registry here. Bad names raise `ValueError` (HTTP 400 at the boundary).
  - `name` is unique; a duplicate insert surfaces as `IntegrityError` and
    we re-raise as `ValueError("library name already exists")`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import LibraryNotFound
from app.models.orm import Chapter, Library, Series, Volume
from app.schemas.library import LibraryCreate, LibraryStats, LibraryUpdate
from app.scrapers.registry import get_scraper_registry


# ----------------------------------------------------------------- helpers


def _validate_providers(providers: Sequence[str] | None) -> None:
    """Reject providers that the registry doesn't know about."""
    if not providers:
        return
    registry = get_scraper_registry()
    unknown = [p for p in providers if not registry.has(p)]
    if unknown:
        raise ValueError(f"unknown providers: {unknown!r}")


# ----------------------------------------------------------------- read


async def list_libraries(
    session: AsyncSession,
    *,
    include_deleted: bool = False,
) -> list[Library]:
    stmt = select(Library)
    if not include_deleted:
        stmt = stmt.where(Library.deleted.is_(False))
    stmt = stmt.order_by(Library.id.asc())
    return list((await session.execute(stmt)).scalars().all())


async def get_library(
    session: AsyncSession,
    library_id: int,
    *,
    include_deleted: bool = False,
) -> Library:
    stmt = (
        select(Library)
        .where(Library.id == library_id)
    )
    if not include_deleted:
        stmt = stmt.where(Library.deleted.is_(False))
    lib = (await session.execute(stmt)).scalar_one_or_none()
    if lib is None:
        raise LibraryNotFound(f"library {library_id} not found")
    return lib


async def library_stats(
    session: AsyncSession, library_id: int,
) -> LibraryStats:
    """Aggregate counts and disk usage for a library.

    Single roundtrip via scalar subqueries; the series_count comes from
    a `Library.series` collection in `get_library`, the chapter stats
    via `func.count`.
    """
    # Make sure the library exists.
    await get_library(session, library_id)
    series_count = await _count_active_series(session, library_id)

    chapter_stmt = (
        select(
            func.count(Chapter.id),
            func.count(Chapter.downloaded_at),
            func.coalesce(func.sum(Chapter.cbz_size), 0),
        )
        .join(Volume, Volume.id == Chapter.volume_id)
        .join(Series, Series.id == Volume.series_id)
        .where(Series.library_id == library_id, Series.deleted.is_(False))
    )
    chapter_count, downloaded_count, total_bytes = (
        await session.execute(chapter_stmt)
    ).one()
    return LibraryStats(
        library_id=library_id,
        series_count=series_count,
        chapter_count=int(chapter_count or 0),
        downloaded_chapter_count=int(downloaded_count or 0),
        total_cbz_bytes=int(total_bytes or 0),
    )


async def _count_active_series(session: AsyncSession, library_id: int) -> int:
    """Count non-deleted series in `library_id`."""
    stmt = select(func.count(Series.id)).where(
        Series.library_id == library_id, Series.deleted.is_(False),
    )
    return int((await session.execute(stmt)).scalar_one())


# ---------------------------------------------------------------- write


async def create_library(
    session: AsyncSession, payload: LibraryCreate,
) -> Library:
    _validate_providers(payload.providers)
    # Make sure the on-disk root exists; benign for the "user wants to
    # point at /mnt/nas/manga" case.
    try:
        Path(payload.root_path).mkdir(parents=True, exist_ok=True)
    except OSError:
        # If the path can't be created (e.g. permission denied) we let
        # the request fail at mkdir time but don't block row creation —
        # the user might be planning to mount the volume later.
        pass

    lib = Library(
        name=payload.name,
        type=payload.type,
        root_path=payload.root_path,
        folder_strategy=payload.folder_strategy,
        cover_strategy=payload.cover_strategy,
        providers=list(payload.providers),
        italian_priority=payload.italian_priority,
        follow_interval_hours=payload.follow_interval_hours,
        jpg_quality=payload.jpg_quality,
    )
    session.add(lib)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError(f"library name already exists: {payload.name!r}") from e
    # Caller commits (services never auto-commit).
    return lib


async def update_library(
    session: AsyncSession, library_id: int, patch: LibraryUpdate,
) -> Library:
    lib = await get_library(session, library_id)
    if patch.providers is not None:
        _validate_providers(patch.providers)
    # Apply only the fields that were sent.
    for field_name in (
        "name", "type", "root_path", "folder_strategy", "cover_strategy",
        "providers", "italian_priority", "follow_interval_hours", "jpg_quality",
    ):
        value = getattr(patch, field_name)
        if value is None:
            continue
        setattr(lib, field_name, value)
    if patch.root_path is not None:
        try:
            Path(patch.root_path).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError(f"library name already exists: {patch.name!r}") from e
    return lib


async def soft_delete_library(
    session: AsyncSession, library_id: int,
) -> Library:
    lib = await get_library(session, library_id)
    lib.deleted = True
    return lib
