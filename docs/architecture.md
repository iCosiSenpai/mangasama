# MangaSama — Architecture

MangaSama is a single FastAPI process that serves a Vue 3 SPA, a REST API, and an OPDS 1.2
catalog, with an in-process scheduler and download workers. State lives in one SQLite database;
CBZ files and covers live on disk.

```
                         ┌──────────────────────────── FastAPI process ───────────────────────────┐
  Browser ──── HTTP ───► │  Vue 3 SPA  (served from /)                                              │
  e-reader ─── OPDS ───► │  /api/*      REST (libraries, series, chapters, search, jobs, settings)  │
                         │  /opds/v1.2/* Atom XML (navigation + acquisition feeds)                  │
                         │                                                                          │
                         │  APScheduler ── follow_check · domain_health · cleanup_jobs              │
                         │  DownloadQueue ── N asyncio workers ──► CbzPackager ──► .cbz on disk     │
                         │  ScraperRegistry ── MangaDex · MangaWorld · (Bato · MangaKakalot · …)    │
                         │  MetadataMerger ── AniList (GraphQL) + MangaDex  (GoogleBooks dormant)    │
                         │  DomainRegistry ── picks the healthy domain per source                   │
                         └──────────────────────────────────────────────────────────────────────────┘
                                    │ aiosqlite                          │ filesystem
                              SQLite (12 tables)                 /data/<library>/… .cbz · /data/covers
```

## Boot order (FastAPI lifespan)

`app/main.py` wires startup in this order (each step is defensive — a partial install still boots):

1. settings (env + `config/default.yaml`) → 2. structured logging → 3. runtime dirs →
4. DB init (`create_all` safety net + re-seed `domain_health` from `sources.yaml`) →
5. shared HTTP client → 6. download queue + workers (`start_download_workers`) →
7. APScheduler (`start_scheduler`). Shutdown drains in reverse.

> In production the Docker entrypoint runs `alembic upgrade head`; `create_all` is only a
> first-run safety net.

## Core flows

### Add a series
`POST /api/search` → the search service queries each provider in `library.providers` in parallel
and returns normalized candidates. `POST /api/series` resolves `(provider, external_id)` via the
scraper, persists a `series` row + a `series_external_ids` mapping, and (by default) runs a
metadata refresh (`AniList` + `MangaDex` merged by `MetadataMerger`, cover cached to disk).

### Follow → download
`follow.check_due_series` (cron) / `POST /api/follow/{id}/check` / `POST /api/series/{id}/backfill`
all funnel through `follow`:
1. pick a usable provider (`series.source_priority` → `library.providers`);
2. list chapters, **Italian-first**, and keep **one chapter per number** (it > en, first upload);
3. diff against existing chapters (idempotency key `(source_provider, source_id, language)`);
4. `enqueue_download(DownloadTask)` for the missing ones.

A `DownloadQueue` worker then (`app/services/downloader.py`): creates a `provider_jobs` row
(short txn, publishes an SSE `running` event) → fetches page URLs + bytes (no DB txn held during
the network I/O) → builds `ComicInfo.xml` → resolves the path via the library's folder strategy →
packs a **deterministic** CBZ (`CbzPackager`) → persists `volumes`/`chapters`/`pages` in a short
txn → marks the job `done`/`error` (publishes the terminal SSE event).

### Read via OPDS
`/opds/v1.2/root` → libraries → library → series **acquisition** feed; each chapter entry links to
`/api/chapters/{id}/file` (`application/vnd.comicbook+zip`). `/opds/v1.2/opensearch.xml` +
`/opds/v1.2/search?q=` search the **local** catalog.

### Domain health / auto-fallback
`domain_health` cron (`app/services/health.py`) pings every enabled source's domains with a
short-timeout, no-retry client and records the outcome via `DomainRegistry`. After 3 consecutive
failures a domain flips `healthy=False`; `DomainRegistry.pick_domain` then routes scrapers to a
healthy alternate. Admin can force a check (`POST /api/settings/providers/health/check`) or clear
a source's failures (`POST /api/settings/providers/{source}/reset`).

## Data model (12 tables)

| Table | Purpose |
|---|---|
| `libraries` | A folder on disk + its content type, providers, folder strategy, follow interval. |
| `series` | A manga/manhua/manhwa in a library (title, status, summary, cover, followed flag). |
| `series_external_ids` | Maps a series to its id on each provider. Unique on `(provider, external_id)`. |
| `series_genres` / `series_tags` | Genre/tag rows per series. |
| `series_authors` | Credited people with a role (writer, penciller, …). |
| `volumes` | Volume of a series. Unique on `(series_id, number, language)`. |
| `chapters` | A chapter. **Idempotency key** `(source_provider, source_id, language)`; holds the CBZ path/size/sha256. |
| `pages` | Per-page rows (filename, source URL, dimensions, sha256). |
| `follow_log` | Audit of follow-check runs. |
| `provider_jobs` | Background jobs (download, …) with status/progress — the SSE/Jobs feed. |
| `domain_health` | Per `(source, domain)` health for auto-fallback. |

## Invariants (do not break)

- **No Lua, no komf.** Scrapers are pure Python (`httpx` + `parsel`/`lxml`); metadata is our own.
- **Italian-first.** For a chapter available in both `it` and `en`, `it` wins (one CBZ per number).
- **Idempotency** by `(source_provider, source_id, language)` — enforced by a DB unique constraint.
- **ComicInfo.xml v2.1** in every CBZ (built only by `ComicInfoBuilder`). See [comicinfo.md](comicinfo.md).
- **Deterministic ZIPs**: every entry timestamped `(1980,1,1,0,0,0)`; zero-padded page names.
- **Domain registry over hardcoded URLs**: edit `config/sources.yaml`, not code. See [sources.md](sources.md).
- **Content types v1**: `manga | manhua | manhwa` only.

See also: [api.md](api.md) · [sources.md](sources.md) · [comicinfo.md](comicinfo.md).
