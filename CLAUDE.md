# CLAUDE.md — MangaSama AI assistant instructions

> Read this first when starting a session on MangaSama. For deep detail see
> `README.md`, `docs/`, and the history log in `ROADMAP.md` §9.

## What this project is

**MangaSama** is a Docker-based, **Italian-first** manga downloader: follow series and have
new chapters auto-downloaded as **CBZ + ComicInfo.xml v2.1**, multi-source scrapers, an
**OPDS 1.2** catalog for e-readers, and a **Vue 3** UI. Backend: Python 3.12 + FastAPI +
SQLAlchemy 2.0 + SQLite (one process, one DB). No Lua, no komf.

**Status: feature-complete.** Build steps 1–17 done, plus optional auth, SQLite backups, and
GitHub Actions CI. The repo is on GitHub at `iCosiSenpai/mangasama` (private). A typical task now
is **deployment, maintenance, or a small enhancement** — not "the next build step".

## Layout (where things live)

```
app/        FastAPI backend
  api/        routers (libraries, series, chapters, search, follow, jobs, settings, covers, opds)
  core/       http client, rate limiter, paths, hashing, auth, exceptions
  db/         engine/session/init (SQLite WAL)
  models/     SQLAlchemy ORM (12 tables, app/models/orm.py)
  schemas/    Pydantic v2 DTOs
  scrapers/   BaseScraper + MangaDex, MangaWorld (+ domain_registry, cookies)
  metadata/   AniList + MangaDex (+ dormant GoogleBooks) + MetadataMerger + cover cache
  services/   downloader, follow, cbz, comicinfo, folder_strategy, language_picker,
              health, backup, opds, library, series, chapter, job_events, settings_api
  scheduler/  APScheduler jobs (follow_check, domain_health, cleanup, backup)
frontend/   Vue 3 + Vite + Tailwind + Pinia (built into app/web/, gitignored)
config/     default.yaml, sources.yaml, logging.yaml
migrations/ Alembic (alembic upgrade head on boot via docker/entrypoint.sh)
docs/       architecture.md, api.md, sources.md, comicinfo.md
docker/     Dockerfile (multi-stage) + entrypoint.sh ; docker-compose.yml at the root
```

## Run it

```bash
# Backend (dev)
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload          # http://localhost:8000

# Frontend (dev)
cd frontend && npm install && npm run build   # builds the SPA into app/web/
#   or `npm run dev` (proxies /api + /opds to :8000)

# Tests / lint
pytest -q                              # backend (mock-based, no network)
ruff check app tests                   # must stay clean (CI gate)
cd frontend && npm run type-check && npm run test && npm run build

# Docker (prod / NAS) — see README "Deploy" + docker-compose.yml
docker compose up -d
```

> Note: the original dev box was Windows where `python` pointed at the Store stub, so commands
> were run as `& "C:\Users\…\Python312\python.exe" -m <cmd>`. On Linux/NAS/CI just use `python`,
> `pytest`, `uvicorn`, `npm`, `docker` directly.

## Deployment (NAS / self-host)

Single container, two persistent volumes (`/data` for the DB + library files, `/config` for
runtime settings/cookies/backups) plus one bind mount per manga folder. `docker compose up -d`
pulls/builds the image, runs migrations via the entrypoint, and serves the SPA + API + OPDS on
`:8000`. See `README.md` (Quickstart / Deploy) and `docs/architecture.md`. On first boot a setup
wizard creates the admin account and initial libraries; most settings are then managed from the GUI
and saved to `/config/settings.yaml`.

## Hard rules — architectural invariants (never break)

1. **No Lua, no komf.** Scrapers are pure Python (`httpx` + `parsel`/`lxml`); metadata is our own.
2. **Single container.** `/data` + `/config` are the only persistent volumes.
3. **Italian-first.** For a chapter available in both `it` and `en`, `it` wins (one CBZ per number).
4. **Idempotency** by `(source_provider, source_id, language)` — enforced by a DB unique constraint.
5. **ComicInfo.xml v2.1** in every CBZ — only via `ComicInfoBuilder` (`app/services/comicinfo.py`).
6. **Deterministic ZIPs**: every entry timestamped `(1980,1,1,0,0,0)`; zero-padded page names.
7. **Domain registry over hardcoded URLs** — edit `config/sources.yaml`, not code.
8. **Content types v1**: `manga | manhua | manhwa` only (reject others at the API boundary with 400).
9. **12-table schema is fixed.** Adding columns is fine; splitting/altering tables needs discussion.
10. **App name is MangaSama**; Docker image `mangasama/mangasama`.

## Conventions

- Python: ruff (line 110, py312); `ruff check app tests` is a CI gate — keep it clean.
  Async everywhere in the request path (`httpx.AsyncClient`, `aiosqlite`). structlog for logging.
  Domain exceptions in `app/core/exceptions.py` → mapped to JSON by `app/api/exception_handlers.py`.
- DB: Alembic migrations (never edit a merged migration); `DateTime(timezone=True)` UTC.
- Frontend: TS strict, Composition API `<script setup>`, Pinia stores, axios via `api/client.ts`,
  lucide icons, vue-sonner toasts. Tests with vitest (`*.spec.ts`).
- Git: small commits, leave the tree runnable; CI (`.github/workflows/ci.yml`) runs pytest +
  frontend type-check/test/build on every push.

## Known open items (optional)

`series_external_ids` is globally unique on `(provider, external_id)` so the same source series
can't yet live in two libraries. See `ROADMAP.md` §9 for the full history and `CHANGELOG.md` for
the release summary.
