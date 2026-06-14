"""`POST /api/search` — multi-source search across `library.providers`."""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import DBSession
from app.schemas.search import SearchRequest, SearchResponse
from app.services import search as search_service

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest, session: DBSession,
) -> SearchResponse:
    return await search_service.multi_source_search(session, payload)
