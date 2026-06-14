"""Series service — CRUD + multi-source search + metadata refresh.

Operations:
  - `list_series` (paged, with filters)
  - `get_series` (with all relationships eager-loaded)
  - `add_series_from_provider` (scrape a series off a remote source and persist it)
  - `update_series`, `soft_delete_series`, `set_followed`
  - `refresh_metadata` (call providers, merge with `MetadataMerger`, write back)
  - `backfill_chapters` (stub — step 11)
  - `multi_source_search` is in `app/services/search.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime

import structlog
from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    LibraryNotFound,
    SeriesNotFoundDB,
)
from app.core.http_client import get_http
from app.metadata import (
    AniListProvider,
    BaseMetadataProvider,
    MangaDexMetadataProvider,
    MergedMetadata,
    MetadataMerger,
    MetadataRecord,
)
from app.metadata.cover_cache import fetch_and_cache
from app.models.orm import (
    Library,
    Series,
    SeriesAuthor,
    SeriesExternalId,
    SeriesGenre,
    SeriesTag,
)
from app.schemas.series import (
    SeriesMetadataRefreshResult,
    SeriesRead,
    SeriesUpdate,
)
from app.scrapers.base import SeriesNotFound as SeriesNotFoundScraper
from app.scrapers.registry import get_scraper
from app.settings import get_settings

logger = structlog.get_logger("mangasama.services.series")


# ----------------------------------------------------------------- helpers


def _sort_title(title: str) -> str:
    """Strip leading articles for a stable alphabetical sort."""
    if not title:
        return ""
    lower = title.lower()
    for prefix in ("the ", "a ", "an "):
        if lower.startswith(prefix):
            return title[len(prefix):]
    return title


async def _build_metadata_providers(
    provider_names: Iterable[str] | None = None,
) -> list[BaseMetadataProvider]:
    """Instantiate the metadata providers we have available.

    Defaults: AniList + MangaDex. GoogleBooks is added only if
    `settings.google_books_enabled` is True.
    """
    settings = get_settings()
    http = get_http()
    available = {
        "anilist": AniListProvider(http=http),
        "mangadex": MangaDexMetadataProvider(http=http),
    }
    if settings.google_books_enabled:
        # Lazy import: the module is dormant in v1.
        from app.metadata.googlebooks import GoogleBooksProvider
        available["google_books"] = GoogleBooksProvider()
    if provider_names is None:
        return [available[k] for k in ("anilist", "mangadex") if k in available]
    return [available[n] for n in provider_names if n in available]


def _apply_merged_to_series(series: Series, merged: MergedMetadata) -> None:
    """Write merged scalars onto the row. Relationships are handled by
    the caller (separate INSERT/DELETE for genres/tags/authors)."""
    if merged.title:
        series.title = merged.title
        series.sort_title = _sort_title(merged.title)
    if merged.alt_titles:
        series.alt_titles = list(merged.alt_titles)
    if merged.summary:
        series.summary = merged.summary
    if merged.year is not None:
        series.year = merged.year
    if merged.status:
        series.status = merged.status
    # Note: `country`, `type` and `publisher` have no column on the
    # `series` row in v1 (the 12-table schema is fixed), so they are not
    # persisted here. `type` is library-scoped; `language` is the closest
    # proxy for country.


async def _replace_collection(
    session: AsyncSession,
    series: Series,
    attr: str,
    model_cls: type,
    values: Iterable[str],
    name_attr: str,
) -> None:
    """Replace a (genre|tag|author) collection on a series.

    `model_cls` is `SeriesGenre` | `SeriesTag`; `name_attr` is `genre` /
    `tag`. For `SeriesAuthor` the function expects a list of
    `(role, name)` pairs and a different signature — see
    `_replace_authors` for that case.

    We mutate the relationship collection (clear + append) rather than
    `session.add`/`delete`, so the in-memory `series` stays in sync with
    the DB — otherwise the caller would read a stale (empty) collection
    from the identity map.
    """
    collection = getattr(series, attr)
    collection.clear()  # delete-orphan cascade removes the old rows
    await session.flush()  # ensure DELETEs run before the re-INSERTs
    seen: set[str] = set()
    for v in values:
        v = (v or "").strip()
        if not v or v in seen:
            continue
        seen.add(v)
        collection.append(model_cls(**{name_attr: v}))


async def _replace_authors(
    session: AsyncSession,
    series: Series,
    authors: Iterable,
) -> None:
    """Replace the authors collection. `authors` items are
    `MetadataAuthor(role, name)`.
    """
    series.authors.clear()  # delete-orphan cascade removes the old rows
    await session.flush()
    seen: set[tuple[str, str]] = set()
    for a in authors:
        role = (a.role or "").strip()
        name = (a.name or "").strip()
        if not role or not name:
            continue
        key = (role, name)
        if key in seen:
            continue
        seen.add(key)
        series.authors.append(SeriesAuthor(role=role, name=name))


# ----------------------------------------------------------------- mapper


def to_series_read(s: Series) -> SeriesRead:
    """Map an ORM `Series` (with relationships loaded) to `SeriesRead`.

    Shared by the API layer (`app/api/series.py:_to_read`) and
    `refresh_metadata` so the response shape is built in exactly one
    place. The ORM exposes genres/tags/authors as rows (not scalars), so
    `SeriesRead.model_validate(s)` would raise — this mapper flattens them.
    """
    return SeriesRead(
        id=s.id,
        library_id=s.library_id,
        title=s.title,
        sort_title=s.sort_title,
        alt_titles=list(s.alt_titles or []),
        status=s.status,
        summary=s.summary,
        year=s.year,
        language=s.language,
        cover_path=s.cover_path,
        source_priority=list(s.source_priority or []),
        followed=s.followed,
        followed_at=s.followed_at,
        last_checked_at=s.last_checked_at,
        created_at=s.created_at,
        updated_at=s.updated_at,
        deleted=s.deleted,
        external_ids=[
            {
                "provider": e.provider,
                "external_id": e.external_id,
                "url": e.url,
                "fetched_at": e.fetched_at,
            }
            for e in (s.external_ids or [])
        ],
        authors=[{"role": a.role, "name": a.name} for a in (s.authors or [])],
        genres=[g.genre for g in (s.genres or [])],
        tags=[t.tag for t in (s.tags or [])],
        volume_count=len(s.volumes or []),
    )


# ----------------------------------------------------------------- read


async def list_series(
    session: AsyncSession,
    *,
    library_id: int | None = None,
    followed: bool | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Series]:
    stmt = select(Series).options(
        selectinload(Series.external_ids),
        selectinload(Series.library),
    )
    stmt = stmt.where(Series.deleted.is_(False))
    if library_id is not None:
        stmt = stmt.where(Series.library_id == library_id)
    if followed is not None:
        stmt = stmt.where(Series.followed.is_(followed))
    if q:
        like = f"%{q.lower()}%"
        # `alt_titles` is a JSON column (TEXT on SQLite); casting to a
        # string lets us substring-match the serialized list.
        stmt = stmt.where(
            or_(
                Series.title.ilike(like),
                cast(Series.alt_titles, String).ilike(like),
            )
        )
    # Default sort: by sort_title, then by id for stability.
    stmt = stmt.order_by(Series.sort_title.asc().nullslast(), Series.id.asc())
    stmt = stmt.limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars().all())


async def get_series(session: AsyncSession, series_id: int) -> Series:
    stmt = (
        select(Series)
        .where(Series.id == series_id, Series.deleted.is_(False))
        .options(
            selectinload(Series.external_ids),
            selectinload(Series.genres),
            selectinload(Series.tags),
            selectinload(Series.authors),
            selectinload(Series.volumes),
        )
    )
    s = (await session.execute(stmt)).scalar_one_or_none()
    if s is None:
        raise SeriesNotFoundDB(f"series {series_id} not found")
    return s


# ---------------------------------------------------------------- write


async def add_series_from_provider(
    session: AsyncSession,
    library_id: int,
    provider: str,
    external_id: str,
    *,
    language: str = "it",
) -> Series:
    """Resolve `external_id` on `provider`, then persist a Series row.

    Steps:
      1. Load the library (404 if missing).
      2. Get the scraper (KeyError if unknown → ConfigError).
      3. Call `scraper.get_series(external_id)` (raises SeriesNotFound
         scraper-side if the id is unknown to the source).
      4. Dedup: if a Series already exists in this library with the
         same title (case-insensitive), reuse it and just add the new
         external_id mapping.
      5. Otherwise, create a fresh Series row + SeriesExternalId row.
    """
    lib_stmt = select(Library).where(
        Library.id == library_id, Library.deleted.is_(False),
    )
    lib = (await session.execute(lib_stmt)).scalar_one_or_none()
    if lib is None:
        raise LibraryNotFound(f"library {library_id} not found")

    try:
        scraper = get_scraper(provider)
    except KeyError as e:
        from app.core.exceptions import ConfigError
        raise ConfigError(f"unknown provider: {provider!r}") from e

    try:
        scraped = await scraper.get_series(external_id)
    except SeriesNotFoundScraper as e:
        # Re-raise as DB-side 404 for the API boundary.
        raise SeriesNotFoundDB(
            f"{provider} has no series with id {external_id!r}"
        ) from e

    # Dedup: by (library_id, lower(title))
    title = scraped.title.strip()
    if not title:
        raise ValueError("scraped series has no title; refusing to add")
    sort_t = _sort_title(title)

    existing_stmt = (
        select(Series)
        .where(Series.library_id == library_id)
        .where(Series.title.ilike(title))
        .options(selectinload(Series.external_ids))
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()

    if existing is not None:
        series = existing
    else:
        series = Series(
            library_id=library_id,
            title=title,
            sort_title=sort_t,
            alt_titles=list(scraped.alt_titles or []),
            status=scraped.status,
            summary=scraped.summary,
            year=scraped.year,
            language=language or None,
            source_priority=list(lib.providers or []),
        )
        session.add(series)
        await session.flush()

    # Insert the external id mapping. Unique on (provider, external_id)
    # means a series added to two libraries shares the same row — but
    # the SeriesExternalId.composite_pk is (series_id, provider), so
    # we use the same provider key. In practice: if the same provider
    # already has an id mapped to a *different* series, we have a
    # conflict — skip with a warning.
    already = await session.execute(
        select(SeriesExternalId).where(
            SeriesExternalId.provider == provider,
            SeriesExternalId.external_id == external_id,
            SeriesExternalId.series_id != series.id,
        )
    )
    if already.scalar_one_or_none() is not None:
        logger.warning(
            "series.add.duplicate_external_id",
            provider=provider, external_id=external_id,
            other_series_id=series.id,
        )
    else:
        existing_eid_stmt = select(SeriesExternalId).where(
            SeriesExternalId.series_id == series.id,
            SeriesExternalId.provider == provider,
        )
        existing_eid = (await session.execute(existing_eid_stmt)).scalar_one_or_none()
        if existing_eid is None:
            session.add(SeriesExternalId(
                series_id=series.id,
                provider=provider,
                external_id=external_id,
                url=scraped.url,
                fetched_at=datetime.now(UTC),
            ))
        else:
            existing_eid.external_id = external_id
            existing_eid.url = scraped.url
            existing_eid.fetched_at = datetime.now(UTC)
    return series


async def update_series(
    session: AsyncSession, series_id: int, patch: SeriesUpdate,
) -> Series:
    s = await get_series(session, series_id)
    if patch.title is not None:
        s.title = patch.title
        s.sort_title = _sort_title(patch.title)
    if patch.sort_title is not None:
        s.sort_title = patch.sort_title
    if patch.alt_titles is not None:
        s.alt_titles = list(patch.alt_titles)
    if patch.status is not None:
        s.status = patch.status
    if patch.summary is not None:
        s.summary = patch.summary
    if patch.year is not None:
        s.year = patch.year
    if patch.language is not None:
        s.language = patch.language
    if patch.cover_path is not None:
        s.cover_path = patch.cover_path
    if patch.source_priority is not None:
        s.source_priority = list(patch.source_priority)
    if patch.followed is not None:
        s.followed = patch.followed
        if patch.followed:
            s.followed_at = datetime.now(UTC)
    return s


async def soft_delete_series(
    session: AsyncSession, series_id: int,
) -> Series:
    s = await get_series(session, series_id)
    s.deleted = True
    return s


async def set_followed(
    session: AsyncSession, series_id: int, followed: bool,
) -> Series:
    s = await get_series(session, series_id)
    s.followed = followed
    s.followed_at = datetime.now(UTC) if followed else None
    return s


# ------------------------------------------------------- metadata refresh


async def refresh_metadata(
    session: AsyncSession,
    series_id: int,
    *,
    providers: list[str] | None = None,
    download_cover: bool = True,
) -> SeriesMetadataRefreshResult:
    """Fetch metadata from one or more providers, merge with the
    MetadataMerger, write the merged result back to the series row.

    Returns a result object with the updated series and the merged dict.
    Never raises on provider failure — we collect whatever worked and
    return a partial result. If no provider returns anything usable,
    the series is left untouched and the `merged` dict will be empty.
    """
    s = await get_series(session, series_id)
    provider_instances = await _build_metadata_providers(providers)

    # We need a SeriesExternalId for each provider to call get_record.
    by_provider: dict[str, SeriesExternalId] = {
        eid.provider: eid for eid in s.external_ids
    }
    # Some providers don't need a pre-existing external id (e.g. they
    # accept the same id format as the search query). For now we only
    # call providers we have an external id for.
    targets = [p for p in provider_instances if p.name in by_provider]

    async def _fetch(p: BaseMetadataProvider) -> MetadataRecord | None:
        ext = by_provider[p.name].external_id
        try:
            return await p.get_record(ext)
        except Exception as e:  # SourceUnavailable, ValueError, ...
            logger.warning(
                "metadata.refresh.provider_failed",
                provider=p.name, external_id=ext, error=str(e),
            )
            return None

    records: list[MetadataRecord] = []
    fetch_results = await asyncio.gather(
        *(_fetch(p) for p in targets), return_exceptions=False,
    )
    records = [r for r in fetch_results if r is not None]
    sources_used = [r.provider for r in records]

    if not records:
        # Nothing worked; return a "no-op" merged record.
        return SeriesMetadataRefreshResult(
            series=to_series_read(s),
            merged=MergedMetadata().to_dict(),
            cover_cached=False,
            sources_used=[],
        )

    merged: MergedMetadata = MetadataMerger().merge(records)

    # Write merged scalars + relationships onto the series.
    _apply_merged_to_series(s, merged)
    await _replace_collection(session, s, "genres", SeriesGenre, merged.genres, "genre")
    await _replace_collection(session, s, "tags", SeriesTag, merged.tags, "tag")
    await _replace_authors(session, s, merged.authors)

    # Cover (only if asked AND there's a cover URL).
    cover_cached = False
    if download_cover and merged.cover_url:
        try:
            # Use the highest-confidence provider as the cache key.
            top_provider = records[0].provider
            top_ext = by_provider[top_provider].external_id
            cached = await fetch_and_cache(
                top_provider, top_ext, merged.cover_url,
            )
            s.cover_path = str(cached)
            cover_cached = True
        except Exception as e:
            logger.warning("metadata.refresh.cover_failed", error=str(e))

    # `_replace_collection`/`_replace_authors` mutate the relationship
    # collections in place, so `s` already reflects the new graph. Flush
    # to persist before the caller commits.
    await session.flush()

    return SeriesMetadataRefreshResult(
        series=to_series_read(s),
        merged=merged.to_dict(),
        cover_cached=cover_cached,
        sources_used=sources_used,
    )


# ----------------------------------------------------------------- stub


async def backfill_chapters(
    session: AsyncSession,
    series_id: int,
    *,
    count: int | None = None,
    language_priority: list[str] | None = None,
) -> dict:
    """Enqueue the series' missing chapters for download.

    Delegates to `app.services.follow.backfill_series` (the download
    engine). Validates the id first so 404s are honest.
    """
    await get_series(session, series_id)
    from app.services import follow
    return await follow.backfill_series(
        session, series_id, count=count, language_priority=language_priority,
    )


__all__ = [
    "add_series_from_provider",
    "backfill_chapters",
    "get_series",
    "list_series",
    "refresh_metadata",
    "set_followed",
    "soft_delete_series",
    "to_series_read",
    "update_series",
]
