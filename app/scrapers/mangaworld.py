"""MangaWorld scraper (HTML, no API).

Site: https://www.mangaworld.mx
Italian-only scanlation aggregator. The site rotates domains every
few months; `config/sources.yaml` keeps a `primary` + `alternates`
list, and `app.scrapers.domain_registry.DomainRegistry.pick_domain`
chooses a healthy one at runtime.

What we use:
  - GET /archive?keyword={q}&type={t}&genre={g}&... — search & filter
  - GET /manga/{id} — series detail + chapter list
  - GET /manga/{id}/{slug}/read/{chapter_id}?style=list — chapter reader

Notes on the HTML structure (MangaWorld is plain Bootstrap 4 with
custom classes — no SPA, no JSON API):

  Series page (`/manga/{id}`):
    <h1 class="name bigger">Title</h1>
    <div class="thumb mb-3"><img class="rounded" src="cdn...mangas/<hash>.jpg" /></div>
    <div class="info">
      <div class="meta-data row px-1">
        <div class="col-12"><span class=font-weight-bold>Generi: </span>
          <a class="badge badge-primary">Azione</a> ...
        </div>
        <div class="col-12 col-md-6"><span class=font-weight-bold>Autore: </span>
          <a href="?author=...">Name</a>
        </div>
        <div class="col-12 col-md-6"><span class=font-weight-bold>Artista: </span>...</div>
        <div class="col-12 col-md-6"><span class=font-weight-bold>Tipo: </span>...</div>
        <div class="col-12 col-md-6"><span class=font-weight-bold>Stato: </span>...</div>
        <div class="col-12 col-md-6"><span class=font-weight-bold>Anno di uscita: </span>...</div>
      </div>
    </div>
    <div class="chapters-wrapper py-2 pl-0">
      <div class="chapter pl-2">
        <a class="chap" href=".../read/{chapter_id}?style=list" title="...">
          <span class="d-inline-block">Capitolo NN</span>
          <i class="chap-date">23 Maggio 2023</i>
        </a>
      </div>
      ...

  Chapter page (`?style=list`):
    <img id="page-N" class="page-image img-fluid" src="https://cdn...chapters/.../<N>.jpg" />

Cloudflare note: the site is behind Cloudflare. Direct HTTP from a
well-known data-centre User-Agent will usually be challenged (403/503).
In Step 15 we wire up the optional Playwright / FlareSolverr solver;
for now we surface the 403/503 as `BlockedByCloudflare` so the
orchestrator can fall back to the next source.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import structlog
from parsel import Selector

from app.core.exceptions import (
    BlockedByCloudflare,
    SeriesNotFound,
    SourceUnavailable,
)
from app.scrapers.base import BaseScraper, ScrapedChapter, ScrapedPage, ScrapedSeries
from app.scrapers.domain_registry import DomainRegistry
from app.settings import get_settings

logger = structlog.get_logger("mangasama.scrapers.mangaworld")

# Italian month names (lowercase) -> month number.
_IT_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}

# Type strings the site shows in the "Tipo:" row -> our ContentType.
_TYPE_MAP = {
    "manga": "manga",
    "manhua": "manhua",
    "manhwa": "manhwa",
    "oneshot": "manga",
    "doujinshi": "manga",
    # MangaWorld also serves thai / vietnamese occasionally — keep as manga
    # for now (no v1 support).
    "thai": "manga",
    "vietnamese": "manga",
}

# Status strings -> our standard set.
_STATUS_MAP = {
    "in corso": "ongoing",
    "finito": "completed",
    "droppato": "cancelled",   # "dropped" is closer to cancelled for our model
    "in pausa": "hiatus",
    "cancellato": "cancelled",
    "paused": "hiatus",
    "ongoing": "ongoing",
    "completed": "completed",
    "dropped": "cancelled",
    "cancelled": "cancelled",
    "hiatus": "hiatus",
}


class MangaWorldScraper(BaseScraper):
    name = "mangaworld"
    display_name = "MangaWorld"
    base_url = "https://www.mangaworld.mx"
    supported_languages = ["it"]
    rate_limit_rpm = 20
    requires_browser = False

    def __init__(self, http: Any = None, *, domain_registry: DomainRegistry | None = None):
        super().__init__(http=http)
        self._registry = domain_registry

    # ---------------------------------------------------------- base URL

    async def _base(self) -> str:
        """Pick the healthy base URL from the domain registry.

        Falls back to `settings.mangaworld_url` (or `base_url`) if the
        registry has no row for this source yet.
        """
        if self._registry is not None:
            try:
                domain = await self._registry.pick_domain(self.name)
            except Exception as e:
                logger.warning("mangaworld.registry_failed", error=str(e))
                domain = None
            if domain:
                return f"https://{domain}"
        s = get_settings()
        # `mangaworld_url` is optional in settings; fall back to base_url.
        return getattr(s, "mangaworld_url", None) or self.base_url

    # -------------------------------------------------------------- helpers

    async def _get_html(self, url: str) -> str:
        """GET `url` and return the body as text. Raises on CF/5xx."""
        domain = urlparse(url).hostname or "www.mangaworld.mx"
        try:
            return await self.http.get_text(
                url,
                scraper=self.name, domain=domain,
                rpm=self._rpm(),
            )
        except SourceUnavailable as e:
            # MangaWorld behind Cloudflare — surface as BlockedByCloudflare
            # so the orchestrator tries the next domain in `alternates`.
            status = e.status_code
            if status in (403, 503):
                raise BlockedByCloudflare(
                    f"{url}: HTTP {status}",
                    source=self.name, url=url,
                ) from e
            raise

    @staticmethod
    def _extract_id(url_or_id: str) -> str:
        """Accept `2906`, `/manga/2906`, or a full URL.

        Returns the numeric ID, or `""` if it can't be extracted.
        """
        if not url_or_id:
            return ""
        s = url_or_id.strip()
        if s.isdigit():
            return s
        # URL path: /manga/2906/...
        m = re.search(r"/manga/(\d+)", s)
        return m.group(1) if m else ""

    @staticmethod
    def _parse_chapter_number(text: str) -> str:
        """`Capitolo 15` -> `15`, `Capitolo 12.5` -> `12.5`."""
        if not text:
            return "0"
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        return m.group(1) if m else "0"

    @staticmethod
    def _parse_italian_date(text: str) -> datetime | None:
        """`23 Maggio 2023` -> datetime(2023, 5, 23). Returns None on failure."""
        if not text:
            return None
        m = re.search(r"(\d{1,2})\s+([A-Za-zàèéìòù]+)\s+(\d{4})", text)
        if not m:
            return None
        day = int(m.group(1))
        month = _IT_MONTHS.get(m.group(2).lower())
        year = int(m.group(3))
        if not month:
            return None
        try:
            return datetime(year, month, day)
        except ValueError:
            return None

    @staticmethod
    def _rpm() -> int:
        return get_settings().mangaworld_rate_limit_rpm

    # ----------------------------------------------------------- health

    async def health_check(self) -> bool:
        base = await self._base()
        url = f"{base}/"
        try:
            html = await self._get_html(url)
        except BlockedByCloudflare:
            return False
        except Exception as e:
            logger.warning("mangaworld.health_failed", error=str(e))
            return False
        # A live page has the brand name in the title.
        return "MangaWorld" in html or "mangaworld" in html.lower()

    # ----------------------------------------------------------- search

    async def search(
        self, query: str, *, limit: int = 20, language: str | None = None,
    ) -> list[ScrapedSeries]:
        """Search MangaWorld.

        IMPORTANT: MangaWorld's archive page is server-rendered but does
        NOT filter by the `keyword` query param — the actual filtering
        happens client-side via JS. We therefore fetch the archive, parse
        every card, and apply a case-insensitive substring filter
        client-side. If the caller passes `query=""` we return whatever
        the archive shows (up to `limit`).
        """
        base = await self._base()
        url = f"{base}/archive?keyword={_q(query)}&type=&genre=&status=&author=&artist=&sort=newest"
        try:
            html = await self._get_html(url)
        except BlockedByCloudflare:
            return []
        sel = Selector(text=html)
        cards = sel.css("div.entry")
        if not cards:
            # Fallback selector: some card types use different markup.
            cards = sel.css("a[href*='/manga/']")

        q = (query or "").strip().lower()
        results: list[ScrapedSeries] = []
        for card in cards:
            series = self._parse_archive_card(card, base_url=base)
            if series is None:
                continue
            if q and q not in series.title.lower():
                continue
            results.append(series)
            if len(results) >= limit:
                break
        return results

    def _parse_archive_card(self, card: Selector, *, base_url: str) -> ScrapedSeries | None:
        """Parse a single archive card. Returns None on parse failure."""
        # The card structure is loose: the first <a> inside the entry
        # usually wraps the cover + title; the title may live in a
        # dedicated <div class="name"> / <h3> / <a> child. We try the
        # most common selectors and finally fall back to the link text.
        href = (card.css("a::attr(href)").get() or "").strip()
        if not href:
            return None
        full_url = urljoin(base_url + "/", href)
        ext_id = self._extract_id(full_url)
        if not ext_id:
            return None

        title = ""
        for sel in (
            ".manga-title::text",
            "h3::text",
            "h2::text",
            ".name::text",
            ".title::text",
            "a::text",
        ):
            t = card.css(sel).get()
            if t:
                title = t.strip()
                if title:
                    break
        if not title:
            # Last resort: first non-empty text node anywhere.
            for t in card.xpath(".//text()[normalize-space()]").getall():
                t = t.strip()
                if t and not t.startswith("/"):
                    title = t
                    break

        cover_url = (card.css("img::attr(src)").get()
                     or card.css("img::attr(data-src)").get())
        if cover_url and cover_url.startswith("/"):
            cover_url = urljoin(base_url + "/", cover_url)

        type_str = (card.css(".type::text").get() or "").strip().lower()
        status_str = (card.css(".status::text").get() or "").strip().lower()
        # Genres can be in `.genre` / `.genres a` / `<a>` filter links.
        genres: list[str] = []
        for sel in (".genre::text", ".genres a::text", ".genres::text"):
            genres.extend([g.strip() for g in card.css(sel).getall() if g.strip()])
        if not genres:
            # Try any <a> whose text doesn't look like a navigation item.
            for g in card.css("a::text").getall():
                g = g.strip()
                if g and len(g) < 30 and not g.startswith("?"):
                    genres.append(g)

        return ScrapedSeries(
            source=self.name,
            external_id=ext_id,
            url=full_url,
            title=title or f"Manga {ext_id}",
            cover_url=cover_url,
            type=_TYPE_MAP.get(type_str, "manga"),
            status=_STATUS_MAP.get(status_str),
            genres=genres,
            metadata={"type_label": type_str, "status_label": status_str},
        )

    # ----------------------------------------------------------- series

    async def get_series(self, url_or_id: str) -> ScrapedSeries:
        ext_id = self._extract_id(url_or_id)
        if not ext_id:
            raise SeriesNotFound(f"Cannot extract MangaWorld ID from {url_or_id!r}")
        base = await self._base()
        url = f"{base}/manga/{ext_id}"
        try:
            html = await self._get_html(url)
        except BlockedByCloudflare as e:
            raise SourceUnavailable(str(e), source=self.name) from e

        sel = Selector(text=html)
        title = (sel.css("h1.name.bigger::text").get() or "").strip()
        if not title:
            raise SeriesNotFound(f"MangaWorld {ext_id}: title not found")

        # Cover image: inside div.thumb.mb3 the only <img>.
        cover_url = sel.css("div.thumb img::attr(src)").get() or sel.css("img.rounded::attr(src)").get()
        if cover_url and cover_url.startswith("/"):
            cover_url = urljoin(base + "/", cover_url)

        # Meta-data fields. We rely on the label text in the
        # `meta-data` block. Each row is a <div class="col-12 ..."> with
        # a leading <span class="font-weight-bold">Label:</span>.
        info: dict[str, str] = {}
        for row in sel.css("div.meta-data > div"):
            label = (row.css("span.font-weight-bold::text").get() or "").strip().rstrip(":").lower()
            # The first <a> in the row carries the human value.
            value = (row.css("a::text").get() or "").strip()
            if label and value:
                info[label] = value

        authors: list[tuple[str, str]] = []
        if "autore" in info:
            authors.append(("writer", info["autore"]))
        if "artista" in info:
            authors.append(("penciller", info["artista"]))

        type_str = info.get("tipo", "manga").lower()
        status_str = info.get("stato", "").lower()
        genres = [g.strip() for g in sel.css(
            "div.meta-data span.font-weight-bold:contains('Generi') + a::text,"
            "div.meta-data span.font-weight-bold:contains('Generi') ~ a::text"
        ).getall() if g.strip()]
        # Fallback: pull every <a class="badge badge-primary"> (the
        # site uses this class for both genres and archive filter links).
        if not genres:
            genres = [g.strip() for g in sel.css(
                "a.badge.badge-primary::text"
            ).getall() if g.strip()]

        # Year.
        year: int | None = None
        if "anno di uscita" in info:
            try:
                year = int(info["anno di uscita"])
            except (TypeError, ValueError):
                year = None

        # Alt titles: the row with label "Titoli alternativi:" has no
        # <a> in our data — the text node of the row carries them,
        # comma-separated.
        alt_titles: list[str] = []
        for row in sel.css("div.meta-data > div"):
            label = (row.css("span.font-weight-bold::text").get() or "").strip().lower()
            if label.startswith("titoli alternativi"):
                raw = "".join(row.css("::text").getall())
                # The label takes a chunk; strip it.
                raw = re.sub(r"^[^\w]+", "", raw).strip()
                alt_titles = [t.strip() for t in raw.split(",") if t.strip()]
                break

        return ScrapedSeries(
            source=self.name,
            external_id=ext_id,
            url=url,
            title=title,
            alt_titles=alt_titles,
            cover_url=cover_url,
            year=year,
            status=_STATUS_MAP.get(status_str),
            type=_TYPE_MAP.get(type_str, "manga"),
            authors=authors,
            genres=genres,
            metadata={"type_label": type_str, "status_label": status_str},
        )

    # ----------------------------------------------------------- chapters

    async def get_chapters(
        self,
        external_id: str,
        *,
        language: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[ScrapedChapter]:
        ext_id = self._extract_id(external_id)
        if not ext_id:
            return []
        base = await self._base()
        url = f"{base}/manga/{ext_id}"
        try:
            html = await self._get_html(url)
        except BlockedByCloudflare:
            return []
        sel = Selector(text=html)

        chapters: list[ScrapedChapter] = []
        for row in sel.css("div.chapters-wrapper div.chapter"):
            a = row.css("a.chap")
            if not a:
                continue
            href = a.css("::attr(href)").get() or ""
            if not href:
                continue
            full_url = urljoin(base + "/", href)
            # The chapter ID for pages() is the URL with `?style=list` already.
            chap_id = full_url  # we use the URL as the ID
            # Number is in the title attr and in <span>.
            title_text = (a.css("::attr(title)").get() or "").strip()
            span_text = (a.css("span::text").get() or "").strip()
            number = self._parse_chapter_number(span_text or title_text)
            date_text = (a.css("i.chap-date::text").get() or "").strip()
            chapters.append(ScrapedChapter(
                source=self.name,
                external_id=chap_id,
                url=full_url,
                number=number,
                title=None,
                language="it",  # MangaWorld ships only Italian scanlations.
                published_at=self._parse_italian_date(date_text),
                scanlation_group=None,
                metadata={"raw_title": title_text, "date_text": date_text},
            ))

        # MangaWorld lists newest first; reverse to oldest-first for our
        # canonical "feed is chronological" contract.
        chapters.reverse()
        if offset:
            chapters = chapters[offset:]
        return chapters[:limit]

    # ------------------------------------------------------------- pages

    async def get_pages(self, chapter_external_id: str) -> list[ScrapedPage]:
        """Fetch the page-image list for a chapter.

        `chapter_external_id` is the chapter URL. We append `?style=list`
        if not present (the URLs from the chapter list already include
        it, but a caller might pass a base URL).
        """
        if not chapter_external_id:
            return []
        url = chapter_external_id
        if "style=list" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}style=list"
        try:
            html = await self._get_html(url)
        except BlockedByCloudflare:
            return []
        sel = Selector(text=html)

        pages: list[ScrapedPage] = []
        for img in sel.css("img.page-image"):
            # The id is "page-N" — we use it as the index, but fall back
            # to the iteration order if the id is missing.
            page_id = img.css("::attr(id)").get() or ""
            m = re.search(r"page-(\d+)", page_id)
            idx = int(m.group(1)) if m else len(pages)
            src = (img.css("::attr(src)").get()
                   or img.css("::attr(data-src)").get()
                   or img.css("::attr(data-original)").get())
            if not src:
                continue
            if src.startswith("/"):
                base = await self._base()
                src = urljoin(base + "/", src)
            # Width/height are not exposed — leave None.
            pages.append(ScrapedPage(index=idx, url=src))

        # Defensive: some chapter pages expose pages in a different
        # order than their index. Re-sort by the numeric id we stored.
        pages.sort(key=lambda p: p.index)
        # Re-pack to 0-based contiguous indices (id may be 0-based or
        # 1-based depending on the page).
        if pages and pages[0].index != 0:
            for i, p in enumerate(pages):
                pages[i] = ScrapedPage(index=i, url=p.url, width=p.width, height=p.height)
        return pages


# ----------------------------------------------------------- small helpers


def _q(s: str) -> str:
    """URL-encode a search query in a parsel-safe way.

    parsel's Selector handles non-ascii fine; this just escapes spaces
    and a few punctuation chars that the archive page's URL parser
    might choke on.
    """
    from urllib.parse import quote_plus
    return quote_plus(s or "")


def _domain_for_log(url: str) -> str:
    try:
        return urlparse(url).hostname or "?"
    except Exception:
        return "?"
