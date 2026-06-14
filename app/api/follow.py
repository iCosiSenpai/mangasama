"""`/api/follow` — list followed series + manually trigger a check."""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import DBSession
from app.schemas.follow import FollowSummary
from app.services import follow as follow_service

router = APIRouter(tags=["follow"])


@router.get("/follow", response_model=list[FollowSummary])
async def list_follows(session: DBSession) -> list[FollowSummary]:
    rows = await follow_service.list_followed_status(session)
    return [
        FollowSummary(
            series_id=s.id,
            library_id=s.library_id,
            title=s.title,
            followed_at=s.followed_at,
            last_checked_at=s.last_checked_at,
            last_status=(log.status if log else None),
            last_new_chapters=(log.new_chapters_count if log else None),
        )
        for s, log in rows
    ]


@router.post("/follow/{series_id}/check")
async def check_follow(series_id: int, session: DBSession) -> dict:
    """Run a follow check now: list chapters, enqueue the missing ones."""
    result = await follow_service.check_series(session, series_id)
    await session.commit()
    return result
