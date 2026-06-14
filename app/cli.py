"""MangaSama CLI — developer-facing helper commands.

Examples:
    python -m app.cli health
    python -m app.cli db-init
    python -m app.cli scrape-test mangadex "death note"
    python -m app.cli metadata "naruto"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import structlog

from app.logging_config import configure_logging

logger = structlog.get_logger("mangasama.cli")


def _cmd_health(_: argparse.Namespace) -> int:
    """Print the cached settings summary."""
    from app.settings import get_settings
    s = get_settings()
    print(json.dumps(
        {
            "app": s.app_name,
            "version": s.app_version,
            "data_dir": str(s.data_dir),
            "config_dir": str(s.config_dir),
            "db_url": s.db_url,
        },
        indent=2,
    ))
    return 0


async def _cmd_db_init(_: argparse.Namespace) -> int:
    from app.db.init import init_db
    await init_db()
    print("DB init OK")
    return 0


async def _cmd_scrape_test(args: argparse.Namespace) -> int:
    """End-to-end: search, fetch series, list chapters and one chapter's pages.

    Usage: `python -m app.cli scrape-test mangadex "death note"`
    """
    from app.core.http_client import start_http, stop_http
    from app.scrapers.base import SeriesNotFound
    from app.scrapers.registry import get_scraper

    try:
        await start_http()
        try:
            scraper = get_scraper(args.source)
        except KeyError as e:
            print(f"error: {e}", file=sys.stderr)
            print(
                f"Available scrapers: {sorted(__import__('app.scrapers.registry', fromlist=['get_scraper_registry']).get_scraper_registry().names())}",
                file=sys.stderr,
            )
            return 2

        print(f"==> searching {scraper.name} for {args.query!r}")
        results = await scraper.search(args.query, limit=min(args.limit, 5))
        if not results:
            print("(no results)")
            return 0
        for i, s in enumerate(results, 1):
            print(f"  {i}. {s.title}  [{s.external_id}]  {s.url}")

        # Pick the first result and drill in.
        chosen = results[0]
        print(f"\n==> series: {chosen.title}")
        full = await scraper.get_series(chosen.external_id)
        print(
            f"    type={full.type} year={full.year} status={full.status} "
            f"authors={full.authors[:3]} genres={full.genres[:5]}"
        )

        print("\n==> chapters (it, en)")
        chapters = await scraper.get_chapters(
            full.external_id, language="it", limit=10,
        )
        if not chapters:
            # Fall back to English.
            chapters = await scraper.get_chapters(
                full.external_id, language="en", limit=10,
            )
        if not chapters:
            print("(no chapters)")
            return 0
        for c in chapters[:10]:
            lang = c.language or "?"
            print(
                f"  ch{c.number}  [{lang}]  {c.title or ''!r}  "
                f"pages={c.pages_count}  {c.external_id}"
            )

        # Pull pages for the first chapter as a final integration check.
        first = chapters[0]
        print(f"\n==> pages for ch{first.number} ({first.external_id})")
        pages = await scraper.get_pages(first.external_id)
        print(f"  {len(pages)} pages; first URL: {pages[0].url if pages else '(none)'}")
        return 0
    except SeriesNotFound as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        await stop_http()


async def _cmd_metadata(args: argparse.Namespace) -> int:
    """Search a query against all enabled metadata providers and merge.

    Usage: `python -m app.cli metadata "naruto"`
    """
    from app.core.http_client import get_http, start_http, stop_http
    from app.metadata.anilist import AniListProvider
    from app.metadata.mangadex import MangaDexMetadataProvider
    from app.metadata.merger import MetadataMerger

    try:
        await start_http()
        http = get_http()
        providers = [AniListProvider(http=http), MangaDexMetadataProvider(http=http)]

        # 1) Search each provider in parallel-ish (sequential is fine for CLI).
        candidates: dict[str, list] = {}
        for p in providers:
            try:
                cs = await p.search(args.query, limit=5)
            except Exception as e:
                logger.warning("metadata.search_failed", provider=p.name, error=str(e))
                cs = []
            candidates[p.name] = cs
            print(f"==> {p.name}: {len(cs)} candidates")

        # 2) Pick the first candidate per provider (or empty if none).
        chosen: dict[str, object] = {}
        for p in providers:
            cs = candidates.get(p.name) or []
            if cs:
                chosen[p.name] = cs[0]
                print(f"    [{p.name}] picked: {cs[0].title} ({cs[0].external_id})")

        if not chosen:
            print("(no candidates from any provider)")
            return 0

        # 3) Fetch full records and merge.
        records = []
        for p in providers:
            if p.name not in chosen:
                continue
            ext = chosen[p.name].external_id
            try:
                records.append(await p.get_record(ext))
            except Exception as e:
                logger.warning("metadata.get_record_failed", provider=p.name, error=str(e))

        if not records:
            print("(no records fetched)")
            return 0

        merged = MetadataMerger().merge(records)
        out = merged.to_dict()
        # Pretty-print.
        print("\n==> MERGED")
        for k, v in out.items():
            if k in ("authors", "genres", "tags", "alt_titles", "available_languages"):
                print(f"  {k}: {v}")
            else:
                print(f"  {k}: {v}")
        return 0
    finally:
        await stop_http()


# ----------------------------------------------------------- library CLI


async def _cmd_library_list(_: argparse.Namespace) -> int:
    from app.db.init import init_db
    from app.db.session import session_scope
    from app.services import library as lib_service

    await init_db()
    async with session_scope() as session:
        libs = await lib_service.list_libraries(session)
        if not libs:
            print("(no libraries)")
            return 0
        for lib in libs:
            # Use a count query to avoid the lazy-load `lib.series`
            # trip, which dies with `MissingGreenlet` because the
            # session's IO machinery isn't in a greenlet context.
            from app.services.library import _count_active_series
            count = await _count_active_series(session, lib.id)
            providers = ",".join(lib.providers or []) or "-"
            print(
                f"  id={lib.id} name={lib.name!r} type={lib.type} "
                f"root={lib.root_path} providers={providers} series={count}"
            )
    return 0


async def _cmd_library_add(args: argparse.Namespace) -> int:
    from app.db.init import init_db
    from app.db.session import session_scope
    from app.schemas.library import LibraryCreate
    from app.services import library as lib_service

    await init_db()
    payload = LibraryCreate(
        name=args.name,
        type=args.type,
        root_path=args.root_path,
        providers=list(args.providers or []),
        folder_strategy=args.folder_strategy,
        italian_priority=not args.no_italian_priority,
        follow_interval_hours=args.follow_interval,
        jpg_quality=args.jpg_quality,
    )
    async with session_scope() as session:
        lib = await lib_service.create_library(session, payload)
        print(
            f"created library id={lib.id} name={lib.name!r} type={lib.type} "
            f"providers={list(lib.providers or [])}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mangasama", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="Show effective settings").set_defaults(func=_cmd_health)
    sub.add_parser("db-init", help="Create tables (safety net)").set_defaults(
        func=lambda a: asyncio.run(_cmd_db_init(a))
    )

    p_scrape = sub.add_parser("scrape-test", help="Scrape a series from a source (step 3)")
    p_scrape.add_argument("source", help="Provider name, e.g. mangadex")
    p_scrape.add_argument("query", help="Series title to search")
    p_scrape.add_argument("--limit", type=int, default=5, help="Max search results (default 5)")
    p_scrape.set_defaults(func=lambda a: asyncio.run(_cmd_scrape_test(a)))

    p_meta = sub.add_parser("metadata", help="Metadata search (step 7)")
    p_meta.add_argument("query", help="Series title to search")
    p_meta.set_defaults(func=lambda a: asyncio.run(_cmd_metadata(a)))

    sub.add_parser("library-list", help="List libraries (step 8)").set_defaults(
        func=lambda a: asyncio.run(_cmd_library_list(a))
    )

    p_libadd = sub.add_parser("library-add", help="Create a library (step 8)")
    p_libadd.add_argument("name", help="Library name (unique)")
    p_libadd.add_argument("root_path", help="On-disk root folder for this library")
    p_libadd.add_argument(
        "--type", choices=["manga", "manhua", "manhwa"], default="manga",
        help="Content type (default: manga)",
    )
    p_libadd.add_argument(
        "--providers", nargs="+", default=None,
        help="Provider names (e.g. mangaworld mangadex)",
    )
    p_libadd.add_argument(
        "--folder-strategy",
        choices=["series_volume_chapter", "series_volume", "chapter_flat", "onefile_per_volume"],
        default="series_volume_chapter",
    )
    p_libadd.add_argument("--follow-interval", type=int, default=24, help="Hours (default 24)")
    p_libadd.add_argument("--jpg-quality", type=int, default=85)
    p_libadd.add_argument(
        "--no-italian-priority", action="store_true",
        help="Disable Italian-first language ordering",
    )
    p_libadd.set_defaults(func=lambda a: asyncio.run(_cmd_library_add(a)))

    args = parser.parse_args(argv)
    configure_logging(level="INFO")
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
