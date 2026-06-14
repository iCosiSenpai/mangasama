"""AniList metadata provider (GraphQL).

API: https://graphql.anilist.co
Public, no auth, 90 req/min rate limit (we use 30 for safety).

What we use:
  - `query Media($search: String, $type: MediaType)` for search
  - The same query with `$id: Int` for direct lookup by AniList ID

Fields we pull (all in a single query, no N+1):
  id, idMal, siteUrl
  title { romaji english native }
  description (asHtml: false — we strip any leftover tags client-side)
  coverImage { extraLarge large color }
  startDate { year }
  status, version
  genres, tags { name }
  staff(perPage: 20) { edges { role node { name { full } } } }
  countryOfOrigin
  type (will become our `manga`/`manhua`/`manhwa` mapping)
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.core.exceptions import SourceUnavailable
from app.metadata.base import (
    BaseMetadataProvider,
    MetadataAuthor,
    MetadataCandidate,
    MetadataRecord,
)

logger = structlog.get_logger("mangasama.metadata.anilist")

_API = "https://graphql.anilist.co"
_TYPE_MAP = {
    "JP": "manga",
    "KR": "manhwa",
    "CN": "manhua",
    "TW": "manhua",
    "HK": "manhua",
}

# AniList returns descriptions wrapped in HTML for formatting. We
# collapse them to plain text + whitespace.
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Author roles that map to ComicInfo v2.1 role names. Anything else
# (translator, original creator, …) is preserved in the role string
# verbatim — ComicInfo is permissive and Komga displays it.
_ROLE_MAP = {
    "story": "writer",
    "story & art": "writer",
    "art": "penciller",
    "illustration": "penciller",
    "writer": "writer",
    "author": "writer",
    "original creator": "writer",
    "penciller": "penciller",
    "inker": "inker",
    "colorist": "colorist",
    "letterer": "letterer",
    "cover": "cover_artist",
    "editor": "editor",
    "translator": "translator",
}


class AniListProvider(BaseMetadataProvider):
    name = "anilist"  # type: ignore[assignment]
    rate_limit_rpm = 30

    # ---------------------------------------------------------------- helpers

    def _rpm(self) -> int:
        from app.settings import get_settings
        return get_settings().anilist_rate_limit_rpm

    def _domain(self) -> str:
        return "graphql.anilist.co"

    async def _gql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        body = {"query": query, "variables": variables}
        try:
            data = await self.http.post_json(
                _API,
                scraper=self.name, domain=self._domain(),
                json_body=body, rpm=self._rpm(),
            )
        except SourceUnavailable as e:
            logger.warning("anilist.gql_failed", error=str(e))
            raise
        if "errors" in data and data["errors"]:
            # AniList uses errors[] for not-found too.
            logger.info("anilist.errors", errors=data["errors"])
        return data or {}

    # --------------------------------------------------------------- search

    async def health_check(self) -> bool:
        # The cheapest probe: a minimal introspection query.
        try:
            data = await self._gql("query { Viewer { id } }", {})
            return "data" in data and (data["data"] or {}).get("Viewer") is not None
        except Exception as e:
            logger.warning("anilist.health_failed", error=str(e))
            return False

    async def search(
        self, query: str, *, limit: int = 10, language: str | None = None,
    ) -> list[MetadataCandidate]:
        gql = """
        query Search($search: String, $perPage: Int) {
          Page(perPage: $perPage) {
            media(search: $search, type: MANGA) {
              id
              siteUrl
              title { romaji english native }
              startDate { year }
              coverImage { extraLarge large color }
              countryOfOrigin
              genres
              tags { name }
              chapters
              volumes
              status
            }
          }
        }
        """
        try:
            data = await self._gql(gql, {"search": query, "perPage": min(limit, 25)})
        except SourceUnavailable:
            return []
        page = (data.get("data") or {}).get("Page") or {}
        results: list[MetadataCandidate] = []
        for m in page.get("media") or []:
            if not m:
                continue
            titles = (m.get("title") or {})
            title = (
                titles.get("english")
                or titles.get("romaji")
                or titles.get("native")
                or ""
            )
            cover = (m.get("coverImage") or {})
            cover_url = cover.get("extraLarge") or cover.get("large")
            results.append(MetadataCandidate(
                provider=self.name,
                external_id=str(m.get("id") or ""),
                url=m.get("siteUrl"),
                title=title,
                alt_titles=[t for t in (titles.get("native"), titles.get("romaji")) if t and t != title],
                year=m.get("startDate", {}).get("year") if m.get("startDate") else None,
                cover_url=cover_url,
                score=1.0 if m.get("chapters") else 0.6,
                available_languages=[],  # AniList doesn't expose per-language availability cheaply
                metadata={
                    "chapters": m.get("chapters"),
                    "volumes": m.get("volumes"),
                    "status": m.get("status"),
                    "country": m.get("countryOfOrigin"),
                    "genres": m.get("genres") or [],
                    "tag_names": [t.get("name") for t in (m.get("tags") or []) if t.get("name")],
                },
            ))
        return results

    # ------------------------------------------------------------- get_record

    async def get_record(self, external_id: str) -> MetadataRecord:
        if not external_id.isdigit():
            raise ValueError(f"AniList external_id must be a numeric ID, got {external_id!r}")
        gql = """
        query ById($id: Int!) {
          Media(id: $id, type: MANGA) {
            id
            siteUrl
            title { romaji english native }
            description(asHtml: false)
            coverImage { extraLarge large color }
            startDate { year }
            endDate { year }
            status
            chapters
            volumes
            countryOfOrigin
            format
            genres
            tags { name }
            staff(perPage: 25) {
              edges { role node { name { full } } }
            }
          }
        }
        """
        data = await self._gql(gql, {"id": int(external_id)})
        m = ((data.get("data") or {}).get("Media"))
        if not m:
            raise SourceUnavailable(f"AniList returned no Media for id={external_id}", source=self.name)

        titles = m.get("title") or {}
        title = titles.get("english") or titles.get("romaji") or titles.get("native") or ""
        cover = m.get("coverImage") or {}
        cover_url = cover.get("extraLarge") or cover.get("large") or cover.get("color")
        country = m.get("countryOfOrigin")
        type_ = _TYPE_MAP.get(country) if country else None
        # `format` from AniList: MANGA, NOVEL, ONE_SHOT. We only want
        # MANGA variants; ONE_SHOT maps to "manga".
        fmt = m.get("format")
        if fmt in ("NOVEL",):
            # No novel support in v1 — return what we can, the merger
            # will discard.
            pass

        authors: list[MetadataAuthor] = []
        for edge in (m.get("staff") or {}).get("edges") or []:
            role = (edge.get("role") or "").strip().lower()
            name = ((edge.get("node") or {}).get("name") or {}).get("full") or ""
            if not name:
                continue
            mapped = _ROLE_MAP.get(role, role or "writer")
            authors.append(MetadataAuthor(role=mapped, name=name))

        return MetadataRecord(
            provider=self.name,
            external_id=str(m.get("id")),
            url=m.get("siteUrl"),
            title=title,
            alt_titles=[t for t in (titles.get("romaji"), titles.get("native")) if t and t != title],
            summary=_clean_html(m.get("description")),
            year=(m.get("startDate") or {}).get("year") if m.get("startDate") else None,
            status=_map_status(m.get("status")),
            cover_url=cover_url,
            country=country,
            type=type_,
            authors=authors,
            genres=list(m.get("genres") or []),
            tags=[t.get("name") for t in (m.get("tags") or []) if t.get("name")],
            available_languages=[],  # we don't query `translations` to stay light
            confidence=0.9,  # AniList is our primary metadata source
            metadata={
                "format": fmt,
                "chapters": m.get("chapters"),
                "volumes": m.get("volumes"),
                "end_year": (m.get("endDate") or {}).get("year") if m.get("endDate") else None,
                "idMal": m.get("idMal"),
            },
        )


# ---------------------------------------------------------- internal helpers


def _clean_html(s: str | None) -> str | None:
    """Strip AniList's HTML wrappers + collapse whitespace."""
    if not s:
        return None
    s = _TAG_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s or None


def _map_status(s: str | None) -> str | None:
    """AniList: RELEASING, FINISHED, NOT_YET_RELEASED, CANCELLED, HIATUS.

    Maps to our standard set: ongoing, completed, hiatus, cancelled, unknown.
    """
    if not s:
        return None
    return {
        "RELEASING": "ongoing",
        "FINISHED": "completed",
        "NOT_YET_RELEASED": "ongoing",
        "CANCELLED": "cancelled",
        "HIATUS": "hiatus",
    }.get(s.upper())
