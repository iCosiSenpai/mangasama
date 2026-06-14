"""OPDS 1.2 catalog endpoints.

Mounted at the app root (prefix ""), so paths are fully qualified
(`/opds/v1.2/...`). Readers (Moon+ Reader, KyBook, Komga, Kavita) browse
these feeds and download CBZs via the acquisition links, which point at
the existing `/api/chapters/{id}/file` endpoint. Links are relative so
they resolve against whatever host serves the feed.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Response

from app.deps import DBSession
from app.services import library as library_service
from app.services import opds
from app.services import series as series_service
from app.services.chapter import list_chapters

router = APIRouter(tags=["opds"], include_in_schema=False)

_V = "/opds/v1.2"


def _xml(feed_el, media_type: str) -> Response:
    return Response(content=opds.serialize(feed_el), media_type=media_type)


@router.get("/opds")
@router.get(_V)
@router.get(f"{_V}/root")
async def opds_root() -> Response:
    f = opds.feed("urn:mangasama:opds:root", "MangaSama", f"{_V}/root", kind="navigation")
    opds.add_link(f, f"{_V}/opensearch.xml", rel="search", type=opds.OPENSEARCH_CT)
    opds.add_nav_entry(f, "urn:mangasama:opds:libraries", "Librerie", f"{_V}/libraries",
                       summary="Sfoglia tutte le librerie")
    opds.add_nav_entry(f, "urn:mangasama:opds:followed", "Seguiti", f"{_V}/followed",
                       summary="Le serie che segui")
    return _xml(f, opds.NAV_CT)


@router.get(f"{_V}/libraries")
async def opds_libraries(session: DBSession) -> Response:
    libs = await library_service.list_libraries(session)
    f = opds.feed("urn:mangasama:opds:libraries", "Librerie", f"{_V}/libraries",
                  kind="navigation", up_href=f"{_V}/root")
    for lib in libs:
        opds.add_nav_entry(
            f, f"urn:mangasama:library:{lib.id}", lib.name,
            f"{_V}/libraries/{lib.id}", summary=lib.type,
        )
    return _xml(f, opds.NAV_CT)


@router.get(f"{_V}/libraries/{{library_id}}")
async def opds_library(library_id: int, session: DBSession) -> Response:
    lib = await library_service.get_library(session, library_id)
    rows = await series_service.list_series(session, library_id=library_id, limit=500)
    f = opds.feed(f"urn:mangasama:library:{library_id}", lib.name,
                  f"{_V}/libraries/{library_id}", kind="navigation", up_href=f"{_V}/libraries")
    for s in rows:
        thumb = f"/api/covers/series/{s.id}" if s.cover_path else None
        opds.add_nav_entry(
            f, f"urn:mangasama:series:{s.id}", s.title,
            f"{_V}/series/{s.id}", summary=s.status or None, thumb_href=thumb,
        )
    return _xml(f, opds.NAV_CT)


@router.get(f"{_V}/series/{{series_id}}")
async def opds_series(series_id: int, session: DBSession) -> Response:
    s = await series_service.get_series(session, series_id)
    chapters = await list_chapters(session, series_id=series_id, downloaded=True, limit=1000)
    thumb = f"/api/covers/series/{s.id}" if s.cover_path else None
    f = opds.feed(f"urn:mangasama:series:{series_id}", s.title,
                  f"{_V}/series/{series_id}", kind="acquisition",
                  up_href=f"{_V}/libraries/{s.library_id}")
    for ch in chapters:
        bits = [f"{s.title} - ch{ch.number}"]
        if ch.title:
            bits.append(ch.title)
        title = " - ".join(bits) + f" ({ch.language})"
        opds.add_acquisition_entry(
            f, f"urn:mangasama:chapter:{ch.id}", title,
            f"/api/chapters/{ch.id}/file",
            size=ch.cbz_size, thumb_href=thumb, updated=ch.downloaded_at,
        )
    return _xml(f, opds.ACQ_CT)


@router.get(f"{_V}/followed")
async def opds_followed(session: DBSession) -> Response:
    rows = await series_service.list_series(session, followed=True, limit=500)
    f = opds.feed("urn:mangasama:opds:followed", "Seguiti", f"{_V}/followed",
                  kind="navigation", up_href=f"{_V}/root")
    for s in rows:
        thumb = f"/api/covers/series/{s.id}" if s.cover_path else None
        opds.add_nav_entry(
            f, f"urn:mangasama:series:{s.id}", s.title,
            f"{_V}/series/{s.id}", thumb_href=thumb,
        )
    return _xml(f, opds.NAV_CT)


@router.get(f"{_V}/opensearch.xml")
async def opds_opensearch() -> Response:
    doc = opds.opensearch_description(f"{_V}/search?q={{searchTerms}}")
    return Response(content=doc, media_type=opds.OPENSEARCH_CT)


@router.get(f"{_V}/search")
async def opds_search(
    session: DBSession,
    q: str = Query(default="", max_length=200),
) -> Response:
    rows = await series_service.list_series(session, q=q, limit=100) if q.strip() else []
    f = opds.feed("urn:mangasama:opds:search", f"Risultati per “{q}”",
                  f"{_V}/search", kind="navigation", up_href=f"{_V}/root")
    for s in rows:
        thumb = f"/api/covers/series/{s.id}" if s.cover_path else None
        opds.add_nav_entry(
            f, f"urn:mangasama:series:{s.id}", s.title,
            f"{_V}/series/{s.id}", thumb_href=thumb,
        )
    return _xml(f, opds.NAV_CT)
