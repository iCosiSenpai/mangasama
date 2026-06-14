# Changelog

All notable changes to MangaSama are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/); this project aims to follow
[Semantic Versioning](https://semver.org/).

## [0.1.0] — unreleased

First functional release. An Italian-first, self-hosted manga downloader.

### Added
- **Multi-library** management (`manga | manhua | manhwa`), each with its own root path,
  provider priority, folder strategy and follow interval.
- **Multi-source search** across providers, Italian-first; **add series** from a provider with
  metadata enrichment (AniList + MangaDex merged by `MetadataMerger`, cover cached on disk).
- **Download engine**: idempotent per-chapter downloader + `DownloadQueue`/workers; deterministic
  **CBZ** output with embedded **ComicInfo.xml v2.1**; four Komga/Kavita folder strategies.
- **Follow scheduler** (APScheduler): periodic `follow_check`, on-demand follow/backfill,
  one chapter per number (Italian wins).
- **Jobs**: `provider_jobs` log + live **SSE** feed (`/api/jobs/stream`) and a Jobs view.
- **OPDS 1.2** catalog (navigation + acquisition feeds + OpenSearch) so e-readers can browse and
  download CBZs; **covers** endpoint.
- **Domain health + auto-fallback**: health cron pings source domains; 3 failures flip a domain
  unhealthy and `DomainRegistry` routes to a healthy alternate; admin check/reset endpoints.
- **Vue 3 SPA**: libraries (create/edit/delete from the UI), search + add, series detail
  (chapters, backfill, follow, covers), jobs (live), settings (effective config + provider health).
- **REST API** with structured error responses; SQLite via Alembic migrations (12 tables).
- **Optional auth**: single-admin HTTP Basic gate over `/api` and `/opds` (`AUTH_ENABLED` +
  `ADMIN_PASSWORD`; `/api/health` stays public), with a frontend login screen.

### Known limitations / roadmap
- **Cloudflare solver** dispatch (Playwright/FlareSolverr) not yet implemented — CF-fronted
  domains currently fail over to the next source.
- **Docker**: multi-stage image + compose + healthcheck + `.dockerignore` are ready; the actual
  `docker compose build && up` is verified at deploy time (NAS). SQLite backup cron still TODO.
- `series_external_ids` is globally unique on `(provider, external_id)`, so the same source series
  can't yet be tracked in two libraries simultaneously.
- Settings are read-only in the UI (the small `PATCH /api/settings` allow-list is API-only).
- MangaEden is disabled (domain defunct as of 2026-06).

See [docs/](docs/) for architecture, API, sources and ComicInfo references.
