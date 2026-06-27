# Changelog

All notable changes to MangaSama are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/); this project aims to follow
[Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-06-27

### Added
- **First-run setup wizard** (`/setup`): admin account (username + bcrypt-hashed password) and initial
  libraries are created from the web UI, not from environment variables.
- **Runtime configuration GUI**: log level, backup, scraper enablement, scheduler intervals,
  Cloudflare solver and FlareSolverr URL are now editable in Settings and persisted to
  `/config/settings.yaml`.
- **Multi-library bind mounts**: `docker-compose.yml` is now production-oriented, with explicit bind
  mounts per manga folder (e.g. `/volume1/manga:/libraries/manga`) and only bootstrap env vars.

### Changed
- **Breaking**: `AUTH_ENABLED` and `ADMIN_PASSWORD` env vars are removed. Auth is mandatory once
  setup completes; credentials are managed via the setup wizard.
- **Breaking**: `BACKUP_ENABLED` and most runtime env vars are removed; configure them in the UI.
- `/opds` now always requires Basic auth after setup (before it was public unless auth was enabled).

## [0.1.0] — 2026-06-27

First functional release. An Italian-first, self-hosted manga downloader.

### Added
- **Multi-library** management (`manga | manhua | manhwa`), each with its own root path,
  provider priority, folder strategy and follow interval.
- **Multi-source search** across **MangaDex** and **MangaWorld** scrapers, Italian-first;
  **add series** from a provider with metadata enrichment (AniList + MangaDex merged by
  `MetadataMerger`, cover cached on disk).
- **Download engine**: idempotent per-chapter downloader + `DownloadQueue`/workers; deterministic
  **CBZ** output with embedded **ComicInfo.xml v2.1**; four Komga/Kavita folder strategies.
- **Follow scheduler** (APScheduler): periodic `follow_check`, on-demand follow/backfill,
  one chapter per number (Italian wins).
- **Jobs**: `provider_jobs` log + live **SSE** feed (`/api/jobs/stream`) and a Jobs view.
- **OPDS 1.2** catalog (navigation + acquisition feeds + OpenSearch) so e-readers can browse and
  download CBZs; **covers** endpoint.
- **Domain health + auto-fallback**: health cron pings source domains; 3 failures flip a domain
  unhealthy and `DomainRegistry` routes to a healthy alternate; admin check/reset endpoints.
- **FlareSolverr Cloudflare bypass** for MangaWorld when `CLOUDFLARE_SOLVER=flaresolverr`.
- **Vue 3 SPA**: libraries (create/edit/delete), search + add, series detail (chapters, backfill,
  follow, redownload), followed-series dashboard, jobs (live SSE with auth), settings (log level +
  provider health actions), toast notifications (vue-sonner).
- **REST API** with structured error responses; SQLite via Alembic migrations (12 tables).
- **Tests & CI**: backend pytest suite + frontend unit tests (vitest); GitHub Actions runs both on every push.
- **Optional auth**: single-admin HTTP Basic gate over `/api` and `/opds` (`AUTH_ENABLED` +
  `ADMIN_PASSWORD`; `/api/health` stays public), with validated login and authenticated downloads.
- **SQLite backups**: WAL-safe online snapshots to `<config>/backups/` with age-based retention.
- **Docker deploy**: entrypoint seeds `/config` YAML from image defaults on first boot.

### Known limitations
- **Tier-2 scrapers** (Bato, MangaKakalot, MangaPark) are registered in `sources.yaml` but have
  no scraper implementation yet.
- **Playwright** CF solver is not implemented (FlareSolverr only).
- `series_external_ids` is globally unique on `(provider, external_id)`, so the same source series
  can't yet be tracked in two libraries simultaneously.
- MangaEden is disabled (domain defunct as of 2026-06).

See [docs/](docs/) for architecture, API, sources and ComicInfo references.
