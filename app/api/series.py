"""`/api/series` — series CRUD + follow + metadata refresh + backfill."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.deps import DBSession
from app.schemas.series import (
    SeriesCreate,
    SeriesListItem,
    SeriesMetadataRefreshRequest,
    SeriesMetadataRefreshResult,
    SeriesRead,
    SeriesUpdate,
)
from app.services import series as series_service

router = APIRouter(tags=["series"])


def _to_read(s) -> SeriesRead:
    """Map an ORM `Series` to the response shape.

    Delegates to the shared `series_service.to_series_read` so the mapping
    lives in exactly one place (also used by `refresh_metadata`).
    """
    return series_service.to_series_read(s)


def _to_list_item(s) -> SeriesListItem:
    return SeriesListItem(
        id=s.id,
        library_id=s.library_id,
        title=s.title,
        sort_title=s.sort_title,
        year=s.year,
        status=s.status,
        cover_path=s.cover_path,
        language=s.language,
        followed=s.followed,
        external_ids=[
            {
                "provider": e.provider,
                "external_id": e.external_id,
                "url": e.url,
                "fetched_at": e.fetched_at,
            }
            for e in (s.external_ids or [])
        ],
    )


@router.get("/series", response_model=list[SeriesListItem])
async def list_series(
    session: DBSession,
    library_id: int | None = Query(default=None, ge=1),
    followed: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[SeriesListItem]:
    rows = await series_service.list_series(
        session, library_id=library_id, followed=followed,
        q=q, limit=limit, offset=offset,
    )
    return [_to_list_item(s) for s in rows]


@router.post(
    "/series",
    response_model=SeriesRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_series(
    payload: SeriesCreate, session: DBSession,
) -> SeriesRead:
    series = await series_service.add_series_from_provider(
        session,
        library_id=payload.library_id,
        provider=payload.provider,
        external_id=payload.external_id,
        language=payload.language or "it",
    )
    if payload.run_metadata_refresh:
        try:
            result = await series_service.refresh_metadata(session, series.id)
            await session.commit()
            return result.series
        except Exception:
            # Provider failure shouldn't block series creation.
            pass
    await session.commit()
    # Re-fetch to populate the read shape.
    full = await series_service.get_series(session, series.id)
    return _to_read(full)


@router.get("/series/{series_id}", response_model=SeriesRead)
async def get_series(series_id: int, session: DBSession) -> SeriesRead:
    s = await series_service.get_series(session, series_id)
    return _to_read(s)


@router.patch("/series/{series_id}", response_model=SeriesRead)
async def update_series(
    series_id: int, patch: SeriesUpdate, session: DBSession,
) -> SeriesRead:
    s = await series_service.update_series(session, series_id, patch)
    await session.commit()
    return _to_read(s)


@router.delete("/series/{series_id}", response_model=SeriesRead)
async def delete_series(
    series_id: int, session: DBSession,
) -> SeriesRead:
    s = await series_service.soft_delete_series(session, series_id)
    await session.commit()
    return _to_read(s)


@router.post("/series/{series_id}/follow", response_model=SeriesRead)
async def follow_series(
    series_id: int, session: DBSession,
) -> SeriesRead:
    s = await series_service.set_followed(session, series_id, True)
    await session.commit()
    return _to_read(s)


@router.post("/series/{series_id}/unfollow", response_model=SeriesRead)
async def unfollow_series(
    series_id: int, session: DBSession,
) -> SeriesRead:
    s = await series_service.set_followed(session, series_id, False)
    await session.commit()
    return _to_read(s)


@router.post("/series/{series_id}/backfill")
async def backfill_series(
    series_id: int,
    session: DBSession,
    count: int | None = Query(default=None, ge=1, le=500),
    language_priority: list[str] | None = Query(default=None),
) -> dict:
    return await series_service.backfill_chapters(
        session, series_id, count=count, language_priority=language_priority,
    )


@router.post(
    "/series/{series_id}/metadata/refresh",
    response_model=SeriesMetadataRefreshResult,
)
async def refresh_metadata(
    series_id: int,
    body: SeriesMetadataRefreshRequest | None = None,
    session: DBSession = None,  # type: ignore[assignment]
) -> SeriesMetadataRefreshResult:
    body = body or SeriesMetadataRefreshRequest()
    result = await series_service.refresh_metadata(
        session, series_id,
        providers=body.providers,
        download_cover=body.download_cover,
    )
    await session.commit()
    return result
