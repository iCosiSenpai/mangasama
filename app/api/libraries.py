"""`/api/libraries` — library CRUD + stats."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.deps import DBSession
from app.schemas.library import (
    LibraryCreate,
    LibraryRead,
    LibraryStats,
    LibraryUpdate,
)
from app.services import library as library_service

router = APIRouter(tags=["libraries"])


def _to_read(lib, series_count: int) -> LibraryRead:
    """Map an ORM `Library` to the response shape.

    `series_count` is computed in the service layer (one aggregate query)
    so the route handler doesn't have to iterate `lib.series`, which
    triggers a sync lazy-load from the closed session and crashes with
    `MissingGreenlet`.
    """
    return LibraryRead(
        id=lib.id,
        name=lib.name,
        type=lib.type,
        root_path=lib.root_path,
        folder_strategy=lib.folder_strategy,
        cover_strategy=lib.cover_strategy,
        providers=list(lib.providers or []),
        italian_priority=lib.italian_priority,
        follow_interval_hours=lib.follow_interval_hours,
        jpg_quality=lib.jpg_quality,
        created_at=lib.created_at,
        updated_at=lib.updated_at,
        deleted=lib.deleted,
        series_count=series_count,
    )


async def _count_series(session, library_id: int) -> int:
    """Return the number of non-deleted series in `library_id`."""
    from sqlalchemy import func, select
    from app.models.orm import Series
    stmt = select(func.count(Series.id)).where(
        Series.library_id == library_id, Series.deleted.is_(False),
    )
    return int((await session.execute(stmt)).scalar_one())


@router.get("/libraries", response_model=list[LibraryRead])
async def list_libraries(session: DBSession) -> list[LibraryRead]:
    libs = await library_service.list_libraries(session)
    out: list[LibraryRead] = []
    for lib in libs:
        out.append(_to_read(lib, await _count_series(session, lib.id)))
    return out


@router.post(
    "/libraries",
    response_model=LibraryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_library(
    payload: LibraryCreate, session: DBSession,
) -> LibraryRead:
    lib = await library_service.create_library(session, payload)
    await session.commit()
    return _to_read(lib, 0)


@router.get("/libraries/{library_id}", response_model=LibraryRead)
async def get_library(library_id: int, session: DBSession) -> LibraryRead:
    lib = await library_service.get_library(session, library_id)
    return _to_read(lib, await _count_series(session, library_id))


@router.patch("/libraries/{library_id}", response_model=LibraryRead)
async def update_library(
    library_id: int, patch: LibraryUpdate, session: DBSession,
) -> LibraryRead:
    lib = await library_service.update_library(session, library_id, patch)
    await session.commit()
    return _to_read(lib, await _count_series(session, library_id))


@router.delete("/libraries/{library_id}", response_model=LibraryRead)
async def delete_library(
    library_id: int, session: DBSession,
) -> LibraryRead:
    lib = await library_service.soft_delete_library(session, library_id)
    await session.commit()
    return _to_read(lib, await _count_series(session, library_id))


@router.get("/libraries/{library_id}/stats", response_model=LibraryStats)
async def library_stats(
    library_id: int, session: DBSession,
) -> LibraryStats:
    return await library_service.library_stats(session, library_id)
