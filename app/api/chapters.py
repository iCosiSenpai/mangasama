"""`/api/chapters` — chapter read + delete + CBZ download."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.deps import DBSession
from app.schemas.chapter import ChapterListItem, ChapterRead
from app.services import chapter as chapter_service

router = APIRouter(tags=["chapters"])


def _to_read(ch) -> ChapterRead:
    return ChapterRead(
        id=ch.id,
        volume_id=ch.volume_id,
        number=ch.number,
        sort=ch.sort,
        title=ch.title,
        source_provider=ch.source_provider,
        source_id=ch.source_id,
        language=ch.language,
        pages_count=ch.pages_count,
        file_path=ch.file_path,
        cbz_size=ch.cbz_size,
        cbz_sha256=ch.cbz_sha256,
        downloaded_at=ch.downloaded_at,
        source_url=ch.source_url,
        comic_info_id=ch.comic_info_id,
        created_at=ch.created_at,
    )


def _to_list_item(ch) -> ChapterListItem:
    return ChapterListItem(
        id=ch.id,
        volume_id=ch.volume_id,
        number=ch.number,
        title=ch.title,
        language=ch.language,
        pages_count=ch.pages_count,
        downloaded_at=ch.downloaded_at,
        cbz_size=ch.cbz_size,
        source_provider=ch.source_provider,
    )


@router.get("/chapters", response_model=list[ChapterListItem])
async def list_chapters(
    session: DBSession,
    series_id: int | None = Query(default=None, ge=1),
    language: str | None = Query(default=None, max_length=8),
    downloaded: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ChapterListItem]:
    rows = await chapter_service.list_chapters(
        session, series_id=series_id, language=language,
        downloaded=downloaded, limit=limit, offset=offset,
    )
    return [_to_list_item(c) for c in rows]


@router.get("/chapters/{chapter_id}", response_model=ChapterRead)
async def get_chapter(
    chapter_id: int, session: DBSession,
) -> ChapterRead:
    ch = await chapter_service.get_chapter(session, chapter_id)
    return _to_read(ch)


@router.get("/chapters/{chapter_id}/file")
async def download_chapter(
    chapter_id: int, session: DBSession,
) -> FileResponse:
    path, filename = await chapter_service.download_chapter_file(
        session, chapter_id,
    )
    return FileResponse(
        path=str(path),
        media_type="application/vnd.comicbook+zip",
        filename=filename,
    )


@router.delete("/chapters/{chapter_id}")
async def delete_chapter(
    chapter_id: int, session: DBSession,
) -> dict:
    await chapter_service.delete_chapter(session, chapter_id)
    await session.commit()
    return {"deleted": True, "id": chapter_id}


@router.post("/chapters/{chapter_id}/redownload")
async def redownload_chapter(
    chapter_id: int, session: DBSession,
) -> dict:
    return await chapter_service.redownload_chapter(session, chapter_id)
