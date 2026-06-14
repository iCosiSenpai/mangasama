# MangaSama — API reference

All JSON endpoints live under `/api`; the OPDS catalog under `/opds/v1.2`. Interactive docs:
**Swagger UI at `/api/docs`**, ReDoc at `/api/redoc`, OpenAPI JSON at `/api/openapi.json`.

Base URL in dev: `http://localhost:8000`.

## Health

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | `{status, app, version, uptime_seconds, data_dir, config_dir}` |

## Libraries

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/libraries` | List libraries (excludes soft-deleted). |
| POST | `/api/libraries` | Create a library. → 201 |
| GET | `/api/libraries/{id}` | Library detail. |
| PATCH | `/api/libraries/{id}` | Partial update. |
| DELETE | `/api/libraries/{id}` | Soft delete (data on disk untouched). |
| GET | `/api/libraries/{id}/stats` | `{series_count, chapter_count, downloaded_chapter_count, total_cbz_bytes}` |

## Search

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/search` | Multi-source search. Body `{library_id, query, providers?, languages?, limit_per_provider?}` → candidates. |

## Series

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/series?library_id=&followed=&q=&limit=&offset=` | List series (filters). |
| POST | `/api/series` | Add a series `{library_id, provider, external_id, language?, run_metadata_refresh?}`. → 201 |
| GET | `/api/series/{id}` | Full series detail (authors, genres, tags, external ids, volume count). |
| PATCH | `/api/series/{id}` | Partial update. |
| DELETE | `/api/series/{id}` | Soft delete. |
| POST | `/api/series/{id}/follow` · `/unfollow` | Toggle follow. |
| POST | `/api/series/{id}/backfill?count=&language_priority=` | Enqueue (latest `count`) missing chapters. → `{scheduled, series_id}` |
| POST | `/api/series/{id}/metadata/refresh` | Re-run the metadata merger; returns the merged record. |

## Chapters

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/chapters?series_id=&language=&downloaded=&limit=&offset=` | List chapters (Italian-first order). |
| GET | `/api/chapters/{id}` | Chapter detail. |
| GET | `/api/chapters/{id}/file` | Download the CBZ (`application/vnd.comicbook+zip`). |
| DELETE | `/api/chapters/{id}` | Delete the chapter row + unlink the CBZ. |
| POST | `/api/chapters/{id}/redownload` | Force a re-download (overwrite). |

## Follow

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/follow` | Followed series + their last check status. |
| POST | `/api/follow/{series_id}/check` | Run a follow check now (enqueue new chapters). |

## Jobs

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/jobs?status=&job_type=&limit=&offset=` | List background jobs (newest first). |
| GET | `/api/jobs/{id}` | Job detail. |
| GET | `/api/jobs/stream` | **SSE** live feed of job state changes (see below). |

### SSE — `/api/jobs/stream`
`Content-Type: text/event-stream`. Each state change is a `data: {json}` frame
(`{id, job_type, provider, status, progress, error, series_id, source_id, language}`); a
`: keepalive` comment is sent every ~15 s. The frontend `JobsView` consumes this.

## Settings & provider health

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/settings` | Effective config (paths, known/enabled scrapers, library defaults). |
| PATCH | `/api/settings` | Runtime override of a small allow-list (`log_level`, `default_rate_limit_rpm`). |
| GET | `/api/settings/providers/health` | Per-source health snapshot. |
| POST | `/api/settings/providers/health/check` | Ping all source domains now and return the snapshot. |
| POST | `/api/settings/providers/{source}/reset` | Clear a source's failure state. |

## Covers

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/covers/series/{id}` | Cached cover image (404 if none; path-traversal guarded). |

## OPDS 1.2 (`/opds/v1.2`)

Atom XML for e-readers (Moon+ Reader, KyBook, Komga, Kavita). Links are relative.

| Path | Kind | Purpose |
|---|---|---|
| `/opds`, `/opds/v1.2`, `/opds/v1.2/root` | navigation | Catalog root (Libraries, Followed, Search link). |
| `/opds/v1.2/libraries` | navigation | One entry per library. |
| `/opds/v1.2/libraries/{id}` | navigation | One entry per series in the library. |
| `/opds/v1.2/series/{id}` | acquisition | One entry per **downloaded** chapter → `/api/chapters/{id}/file`. |
| `/opds/v1.2/followed` | navigation | Followed series. |
| `/opds/v1.2/opensearch.xml` | — | OpenSearch description (`search?q={searchTerms}`). |
| `/opds/v1.2/search?q=` | navigation | Search the local catalog by title. |

## Error format

Domain errors are returned as JSON `{"detail": "...", "type": "...", ...}`:

| HTTP | `type` | Raised when |
|---|---|---|
| 400 | `validation_error` | Request body/query failed Pydantic validation (includes `errors`). |
| 400 | `config_error` | Bad configuration, e.g. unknown provider / series with no usable provider. |
| 400 | `invalid_value` | A `ValueError` (e.g. duplicate library name). |
| 404 | `library_not_found` / `series_not_found` / `chapter_not_found` | Missing (or soft-deleted) resource. |
| 429 | `rate_limited` | Upstream 429 (includes `retry_after` + `Retry-After` header). |
| 502 | `blocked_by_cloudflare` / `source_unavailable` | Upstream blocked/unreachable (includes `source`). |
| 500 | `internal_error` / `unhandled` | Unexpected error. |
