"""Multi-source search service.

Walks `library.providers` (or a caller-supplied subset), asks each
scraper for candidates in parallel, and returns a normalized response.

For series-level search today, the orchestrator can't really know which
candidates have an Italian translation — that's a chapter-level fact.
We expose `is_italian_available` for forward-compat (chapter search in
step 11 will set it).
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import LibraryNotFound
from app.models.orm import Library
from app.schemas.search import SearchCandidate, SearchRequest, SearchResponse
from app.scrapers.registry import get_scraper
from app.scrapers.source_policy import is_scraper_available

logger = structlog.get_logger("mangasama.services.search")


async def multi_source_search(
    session: AsyncSession, req: SearchRequest,
) -> SearchResponse:
    lib_stmt = select(Library).where(
        Library.id == req.library_id, Library.deleted.is_(False),
    )
    lib = (await session.execute(lib_stmt)).scalar_one_or_none()
    if lib is None:
        raise LibraryNotFound(f"library {req.library_id} not found")

    # Provider resolution: explicit list wins; otherwise library.providers.
    candidates = req.providers if req.providers is not None else list(lib.providers)
    # Keep only known, enabled providers.
    providers = [name for name in candidates if is_scraper_available(name)]
    if not providers:
        return SearchResponse(
            query=req.query,
            library_id=req.library_id,
            providers_used=[],
            candidates=[],
        )

    async def _run(name: str) -> list[SearchCandidate]:
        try:
            scraper = get_scraper(name)
        except KeyError as e:
            logger.warning("search.unknown_provider", provider=name, error=str(e))
            return []
        try:
            results = await scraper.search(
                req.query,
                limit=req.limit_per_provider,
                language=req.languages[0] if req.languages else None,
            )
        except Exception as e:
            # A single provider being down shouldn't fail the whole
            # search; log and move on.
            logger.warning("search.provider_failed", provider=name, error=str(e))
            return []
        out: list[SearchCandidate] = []
        for s in results:
            langs = []
            md = getattr(s, "metadata", None) or {}
            if isinstance(md, dict):
                langs = md.get("available_languages") or []
            out.append(SearchCandidate(
                provider=name,
                external_id=s.external_id,
                url=s.url,
                title=s.title,
                alt_titles=list(s.alt_titles or []),
                year=s.year,
                cover_url=s.cover_url,
                language=None,  # series-level search; chapter search sets it
                type=getattr(s, "type", None),
                score=getattr(s, "score", 0.0) or 0.0,
                is_italian_available="it" in (langs or []),
            ))
        return out

    nested = await asyncio.gather(*(_run(n) for n in providers))
    flat = [c for sub in nested for c in sub]
    # Stable order: keep insertion (which follows provider priority).
    return SearchResponse(
        query=req.query,
        library_id=req.library_id,
        providers_used=providers,
        candidates=flat,
    )
