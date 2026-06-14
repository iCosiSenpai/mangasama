"""`/api/covers` — serve cached series cover images."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.deps import DBSession
from app.services import series as series_service
from app.settings import get_settings

router = APIRouter(tags=["covers"])

_MEDIA_BY_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


@router.get("/covers/series/{series_id}")
async def get_series_cover(series_id: int, session: DBSession) -> FileResponse:
    s = await series_service.get_series(session, series_id)  # 404 if missing
    if not s.cover_path:
        raise HTTPException(status_code=404, detail="series has no cover")

    covers_root = get_settings().covers_path.resolve()
    path = Path(s.cover_path).resolve()
    # Anti path-traversal: only ever serve files inside the covers cache.
    if covers_root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="cover not found")

    media = _MEDIA_BY_EXT.get(path.suffix.lstrip(".").lower(), "application/octet-stream")
    return FileResponse(str(path), media_type=media)
