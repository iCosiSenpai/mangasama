"""MangaDex metadata provider.

Distinct from `app.scrapers.mangadex` (which fetches chapter bytes).
This one enriches the series record: tags, demographics, last volume /
chapter, alt titles. It re-uses the same REST endpoints but maps a
different subset of fields.

Reuses `app.scrapers.mangadex.MangaDexScraper._parse_series` for the
common parsing path, so a metadata record and a scraper hit stay in
sync (same alt-titles, same cover, same authors).
"""

from __future__ import annotations

from typing import Any

import structlog

from app.core.exceptions import SeriesNotFound, SourceUnavailable
from app.metadata.base import (
    BaseMetadataProvider,
    MetadataAuthor,
    MetadataCandidate,
    MetadataRecord,
)

logger = structlog.get_logger("mangasama.metadata.mangadex")

_TYPE_MAP = {
    "ja": "manga",
    "ko": "manhwa",
    "zh": "manhua",
    "zh-hk": "manhua",
    "zh-tw": "manhua",
}


class MangaDexMetadataProvider(BaseMetadataProvider):
    name = "mangadex"  # type: ignore[assignment]
    rate_limit_rpm = 40

    def __init__(self, http: Any = None, *, _scraper: Any = None):
        # `_scraper` is an optional pre-built MangaDexScraper we can
        # piggy-back on (for tests + to share the HTTP client).
        super().__init__(http=http)
        self._scraper = _scraper

    # ---------------------------------------------------------------- helpers

    def _api(self) -> str:
        from app.settings import get_settings
        return get_settings().mangadex_url.rstrip("/")

    def _rpm(self) -> int:
        from app.settings import get_settings
        return get_settings().mangadex_rate_limit_rpm

    async def _scraper_instance(self) -> Any:
        if self._scraper is None:
            from app.scrapers.mangadex import MangaDexScraper
            self._scraper = MangaDexScraper(http=self.http)
        return self._scraper

    # ------------------------------------------------------------- search

    async def health_check(self) -> bool:
        try:
            text = await self.http.get_text(
                f"{self._api()}/ping",
                scraper=self.name, domain="api.mangadex.org",
                rpm=self._rpm(),
            )
            return text.strip().lower() == "pong"
        except Exception as e:
            logger.warning("mangadex_meta.health_failed", error=str(e))
            return False

    async def search(
        self, query: str, *, limit: int = 10, language: str | None = None,
    ) -> list[MetadataCandidate]:
        # Reuse the scraper's search — it already returns a typed
        # `ScrapedSeries` that we can lift into a `MetadataCandidate`.
        sc = await self._scraper_instance()
        try:
            results = await sc.search(query, limit=min(limit, 25), language=language)
        except SourceUnavailable:
            return []
        return [
            MetadataCandidate(
                provider=self.name,
                external_id=r.external_id,
                url=r.url,
                title=r.title,
                alt_titles=list(r.alt_titles),
                year=r.year,
                cover_url=r.cover_url,
                # MangaDex doesn't expose a numeric relevance score.
                score=0.6,
                available_languages=[language] if language else [],
                metadata={"status": r.status, "type": r.type},
            )
            for r in results
        ]

    # ----------------------------------------------------------- get_record

    async def get_record(self, external_id: str) -> MetadataRecord:
        if not external_id or len(external_id) != 36 or external_id.count("-") != 4:
            raise SeriesNotFound(
                f"Invalid MangaDex UUID: {external_id!r}",
            )
        try:
            data = await self.http.get_json(
                f"{self._api()}/manga/{external_id}",
                scraper=self.name, domain="api.mangadex.org",
                params={"includes[]": ["cover_art", "author", "artist"]},
                rpm=self._rpm(),
            )
        except SourceUnavailable:
            raise
        if not data.get("data"):
            raise SeriesNotFound(f"MangaDex returned no data for {external_id!r}")

        m = data["data"]
        attrs = m.get("attributes") or {}
        rels = self._index_rels(m.get("relationships") or [])

        title = (
            (attrs.get("title") or {}).get("en")
            or (attrs.get("title") or {}).get("ja")
            or next(iter((attrs.get("title") or {}).values()), "")
        )
        alt_titles: list[str] = []
        for entry in attrs.get("altTitles") or []:
            for v in (entry or {}).values():
                if v and v != title and v not in alt_titles:
                    alt_titles.append(v)

        # Authors — both "author" and "artist" rels; role = "writer" / "penciller".
        authors: list[MetadataAuthor] = []
        seen: set[tuple[str, str]] = set()
        for role, key in (("writer", "author"), ("penciller", "artist")):
            for rel in rels.get(key, []):
                name = (rel.get("attributes") or {}).get("name")
                if not name:
                    continue
                pair = (role, name)
                if pair in seen:
                    continue
                seen.add(pair)
                authors.append(MetadataAuthor(role=role, name=name))

        # Cover.
        cover_url = self._cover_url(rels.get("cover_art", []))

        # Genres (MangaDex groups tags by `group`; genres are `group: "genre"`).
        genres: list[str] = []
        tags: list[str] = []
        for tag in (attrs.get("tags") or []):
            name = self._tag_name(tag)
            if not name:
                continue
            if (tag.get("attributes") or {}).get("group") == "genre":
                if name not in genres:
                    genres.append(name)
            else:
                if name not in tags:
                    tags.append(name)

        return MetadataRecord(
            provider=self.name,
            external_id=m.get("id", ""),
            url=f"https://mangadex.org/title/{m.get('id', '')}",
            title=title,
            alt_titles=alt_titles,
            summary=(attrs.get("description") or {}).get("en"),
            year=self._int(attrs.get("year")),
            status=self._map_status(attrs.get("status")),
            cover_url=cover_url,
            country=attrs.get("originalLanguage"),
            type=_TYPE_MAP.get((attrs.get("originalLanguage") or "").lower()),
            authors=authors,
            genres=genres,
            tags=tags,
            available_languages=[],  # not exposed in the metadata endpoint
            confidence=0.85,  # MangaDex is a strong second to AniList
            metadata={
                "lastChapter": attrs.get("lastChapter"),
                "lastVolume": attrs.get("lastVolume"),
                "demographic": attrs.get("publicationDemographic"),
                "contentRating": attrs.get("contentRating"),
            },
        )

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _int(v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _tag_name(tag: dict[str, Any]) -> str:
        name = (tag.get("attributes") or {}).get("name") or {}
        if isinstance(name, dict):
            return name.get("en") or name.get("it") or next(iter(name.values()), "")
        return str(name)

    @staticmethod
    def _cover_url(cover_rels: list[dict[str, Any]]) -> str | None:
        if not cover_rels:
            return None
        fn = (cover_rels[0].get("attributes") or {}).get("fileName")
        if not fn:
            return None
        return f"https://uploads.mangadex.org/covers/{cover_rels[0].get('id', '')}/{fn}"

    @staticmethod
    def _index_rels(rels: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rels:
            out.setdefault(r.get("type", ""), []).append(r)
        return out

    @staticmethod
    def _map_status(s: str | None) -> str | None:
        return {
            "ongoing": "ongoing",
            "completed": "completed",
            "hiatus": "hiatus",
            "cancelled": "cancelled",
        }.get((s or "").lower())
