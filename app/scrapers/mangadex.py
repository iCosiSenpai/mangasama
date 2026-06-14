"""MangaDex scraper (REST, no auth).

API base: https://api.mangadex.org
Public docs: https://api.mangadex.org/docs/

What we use:
  - GET /manga?title={q}&limit=20&includes[]=cover_art           — search
  - GET /manga/{id}?includes[]=author,artist,cover_art          — series detail
  - GET /manga/{id}/feed?translatedLanguage[]=it&translatedLanguage[]=en&order[chapter]=asc&limit=500
                                                                — chapters
  - GET /at-home/server/{chapterId}                             — page URLs

The `at-home` base URL expires in ~15 minutes, so we re-fetch on each
download (handled in step 11, not here).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import structlog

from app.core.exceptions import SeriesNotFound, SourceUnavailable
from app.scrapers.base import BaseScraper, ScrapedChapter, ScrapedPage, ScrapedSeries
from app.settings import get_settings

logger = structlog.get_logger("mangasama.scrapers.mangadex")


class MangaDexScraper(BaseScraper):
    name = "mangadex"
    display_name = "MangaDex"
    base_url = "https://api.mangadex.org"
    supported_languages = ["en", "it", "ja", "ko", "zh", "fr", "de", "es", "pt"]
    rate_limit_rpm = 40  # MangaDex permits 40 req/min unauthenticated
    requires_browser = False

    # ---------------------------------------------------------------- helpers

    def _api(self) -> str:
        return get_settings().mangadex_url.rstrip("/")

    def _rpm(self) -> int:
        return get_settings().mangadex_rate_limit_rpm

    # ---------------------------------------------------------------- health

    async def health_check(self) -> bool:
        try:
            text = await self.http.get_text(
                f"{self._api()}/ping",
                scraper=self.name, domain="api.mangadex.org",
                rpm=self._rpm(),
            )
            return text.strip().lower() == "pong"
        except Exception as e:
            logger.warning("mangadex.health_failed", error=str(e))
            return False

    # ---------------------------------------------------------------- search

    async def search(
        self, query: str, *, limit: int = 20, language: str | None = None,
    ) -> list[ScrapedSeries]:
        params: dict[str, Any] = {
            "title": query,
            "limit": min(limit, 100),
            "includes[]": ["cover_art", "author", "artist"],
            "availableTranslatedLanguage[]": (language or "it").lower(),
        }
        # MangaDex also accepts a global language filter at the manga level.
        # We don't add a second `availableTranslatedLanguage[]` here because
        # `[]` style params aren't naturally handled by httpx; we OR by
        # calling the endpoint again if the first page is empty. For now
        # we keep it single-language; the orchestrator falls back to other
        # sources if this returns nothing.
        try:
            data = await self.http.get_json(
                f"{self._api()}/manga",
                scraper=self.name, domain="api.mangadex.org",
                params=params, rpm=self._rpm(),
            )
        except SourceUnavailable as e:
            logger.warning("mangadex.search_failed", q=query, error=str(e))
            return []

        return [self._parse_series(m) for m in (data.get("data") or [])]

    # ---------------------------------------------------------------- series

    async def get_series(self, url_or_id: str) -> ScrapedSeries:
        # Accept either a full URL or a raw UUID.
        mid = self._extract_id(url_or_id)
        if not mid:
            raise SeriesNotFound(f"Cannot extract MangaDex ID from {url_or_id!r}")
        try:
            data = await self.http.get_json(
                f"{self._api()}/manga/{mid}",
                scraper=self.name, domain="api.mangadex.org",
                params={"includes[]": ["cover_art", "author", "artist"]},
                rpm=self._rpm(),
            )
        except SourceUnavailable:
            raise
        if not data.get("data"):
            raise SeriesNotFound(f"MangaDex returned no data for {mid!r}")
        return self._parse_series(data["data"])

    # -------------------------------------------------------------- chapters

    async def get_chapters(
        self,
        external_id: str,
        *,
        language: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[ScrapedChapter]:
        mid = self._extract_id(external_id)
        if not mid:
            return []
        langs = self._language_filters(language)
        params: dict[str, Any] = {
            "limit": min(limit, 500),
            "offset": offset,
            "order[chapter]": "asc",
            "includes[]": ["scanlation_group"],
        }
        for lang in langs:
            params.setdefault("translatedLanguage[]", []).append(lang)
        try:
            data = await self.http.get_json(
                f"{self._api()}/manga/{mid}/feed",
                scraper=self.name, domain="api.mangadex.org",
                params=params, rpm=self._rpm(),
            )
        except SourceUnavailable as e:
            logger.warning("mangadex.chapters_failed", mid=mid, error=str(e))
            return []
        return [self._parse_chapter(c) for c in (data.get("data") or [])]

    # ----------------------------------------------------------------- pages

    async def get_pages(self, chapter_external_id: str) -> list[ScrapedPage]:
        # The "external_id" for a chapter at the page-fetch stage is the
        # MangaDex chapter UUID.
        cid = self._extract_id(chapter_external_id)
        if not cid:
            return []
        try:
            data = await self.http.get_json(
                f"{self._api()}/at-home/server/{cid}",
                scraper=self.name, domain="api.mangadex.org",
                rpm=self._rpm(),
            )
        except SourceUnavailable as e:
            logger.warning("mangadex.pages_failed", cid=cid, error=str(e))
            return []

        base = data.get("baseUrl", "").rstrip("/")
        chapter_hash = data.get("chapter", {}).get("hash", "")
        filenames = data.get("chapter", {}).get("data") or []
        # If data is empty, the chapter is reported as "external" (e.g. hosted
        # on the source site) and the downloader should fall back. We still
        # return what we have.
        pages: list[ScrapedPage] = []
        for i, fn in enumerate(filenames):
            pages.append(ScrapedPage(
                index=i,
                url=f"{base}/data/{chapter_hash}/{fn}",
            ))
        return pages

    # ------------------------------------------------------------- parsing

    def _parse_series(self, m: dict[str, Any]) -> ScrapedSeries:
        attrs = m.get("attributes") or {}
        rels = self._index_relationships(m.get("relationships") or [])

        alt_titles: list[str] = []
        for entry in attrs.get("altTitles") or []:
            for v in entry.values():
                if v and v not in alt_titles:
                    alt_titles.append(v)

        # Authors: prefer explicit "author" + "artist" relationships.
        authors: list[tuple[str, str]] = []
        for rel in rels.get("author", []) + rels.get("artist", []):
            name = (rel.get("attributes") or {}).get("name")
            if not name:
                continue
            role = "writer" if rel in rels.get("author", []) else "penciller"
            if (role, name) not in authors:
                authors.append((role, name))

        cover_url = self._cover_url(rels.get("cover_art", []))

        return ScrapedSeries(
            source=self.name,
            external_id=m.get("id", ""),
            url=f"https://mangadex.org/title/{m.get('id', '')}",
            title=(attrs.get("title") or {}).get("en")
                 or (attrs.get("title") or {}).get("ja")
                 or next(iter((attrs.get("title") or {}).values()), ""),
            alt_titles=alt_titles,
            summary=(attrs.get("description") or {}).get("en"),
            year=self._extract_year(attrs.get("year")),
            status=attrs.get("status"),
            cover_url=cover_url,
            authors=authors,
            genres=[self._tag_name(g) for g in (attrs.get("tags") or []) if self._is_genre(g)],
            tags=[self._tag_name(t) for t in (attrs.get("tags") or []) if not self._is_genre(t)],
            type=self._map_type(attrs.get("originalLanguage")),
            metadata={
                "lastChapter": attrs.get("lastChapter"),
                "lastVolume": attrs.get("lastVolume"),
                "demographic": attrs.get("publicationDemographic"),
                "contentRating": attrs.get("contentRating"),
            },
        )

    def _parse_chapter(self, c: dict[str, Any]) -> ScrapedChapter:
        attrs = c.get("attributes") or {}
        rels = self._index_relationships(c.get("relationships") or [])
        groups = rels.get("scanlation_group", [])
        scanlation = (groups[0].get("attributes") or {}).get("name") if groups else None
        published = attrs.get("publishedAt")
        return ScrapedChapter(
            source=self.name,
            external_id=c.get("id", ""),
            url=f"https://mangadex.org/chapter/{c.get('id', '')}",
            number=attrs.get("chapter") or "0",
            title=attrs.get("title"),
            language=(attrs.get("translatedLanguage") or "en").lower(),
            volume_number=attrs.get("volume"),
            pages_count=attrs.get("pages"),
            published_at=self._parse_dt(published) if published else None,
            scanlation_group=scanlation,
            metadata={
                "externalUrl": attrs.get("externalUrl"),
            },
        )

    @staticmethod
    def _extract_id(s: str) -> str:
        """Accept either a raw UUID or a URL like `.../mangadex.org/title/UUID/`."""
        if not s:
            return ""
        # Already a UUID? MangaDex IDs are 36 chars with hyphens.
        if len(s) == 36 and s.count("-") == 4:
            return s
        # Try URL parse.
        from urllib.parse import urlparse
        parts = urlparse(s).path.strip("/").split("/")
        # Last segment that looks like a UUID.
        for p in reversed(parts):
            if len(p) == 36 and p.count("-") == 4:
                return p
        return ""

    @staticmethod
    def _language_filters(language: str | None) -> list[str]:
        if not language:
            return ["it", "en"]
        if language.lower() in {"it", "en"}:
            return [language.lower(), "en" if language.lower() == "it" else "it"]
        return [language.lower()]

    @staticmethod
    def _index_relationships(rels: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rels:
            out.setdefault(r.get("type", ""), []).append(r)
        return out

    @staticmethod
    def _cover_url(cover_rels: list[dict[str, Any]]) -> str | None:
        if not cover_rels:
            return None
        fn = (cover_rels[0].get("attributes") or {}).get("fileName")
        if not fn:
            return None
        return f"https://uploads.mangadex.org/covers/{cover_rels[0].get('id', '')}/{fn}"

    @staticmethod
    def _extract_year(year: Any) -> int | None:
        if year is None:
            return None
        try:
            return int(year)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_genre(tag: dict[str, Any]) -> bool:
        # MangaDex groups its tags; genres are `group: "genre"`.
        return (tag.get("attributes") or {}).get("group") == "genre"

    @staticmethod
    def _tag_name(tag: dict[str, Any]) -> str:
        """Best-effort localized name for a tag.

        MangaDex returns tag names as `{en: "...", it: "...", ...}`. We
        prefer English, then Italian, then whatever's there, then "".
        """
        name = (tag.get("attributes") or {}).get("name") or {}
        if isinstance(name, dict):
            return name.get("en") or name.get("it") or next(iter(name.values()), "")
        return str(name)

    @staticmethod
    def _map_type(original_language: str | None) -> Literal["manga", "manhua", "manhwa"]:
        mapping = {
            "ja": "manga",
            "ko": "manhwa",
            "zh": "manhua",
            "zh-hk": "manhua",
            "zh-tw": "manhua",
        }
        if not original_language:
            return "manga"
        return mapping.get(original_language.lower(), "manga")

    @staticmethod
    def _parse_dt(s: str) -> datetime:
        # MangaDex returns RFC3339 (e.g. "2024-08-15T10:42:18+00:00").
        try:
            from datetime import datetime as _dt
            return _dt.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min
