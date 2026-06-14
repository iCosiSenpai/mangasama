# MangaSama — Build Roadmap

> **PERSISTENT SESSION GUIDE** — Read this file FIRST whenever you start a new
> AI session on the MangaSama project. It is the single source of truth for
> build progress and the agreed implementation plan.
>
> The full architectural plan lives at
> `.claude/plans/g-dev-mangadownloader-voglio-creare-floating-hartmanis.md`
> (the AI may consult it for detail). This file is the **executive view**:
> what has been done, what's next, what conventions to follow, and the
> critical commands / checkpoints.

---

## 0. TL;DR

**MangaSama** is a Docker-based, Italian-first manga downloader with a follow/like scheduler, multi-source scrapers, CBZ+ComicInfo output, OPDS 1.2 catalog, and a Vue 3 UI — built from scratch in Python 3.12 + FastAPI + SQLite, single Docker container, no Lua, no komf.

| Field | Value |
|---|---|
| Project root | `F:\dev\mangadownloader` (Windows) |
| App name | `MangaSama` |
| Backend | Python 3.12+ / FastAPI / httpx / parsel / SQLAlchemy 2.0 / SQLite / APScheduler |
| Frontend | Vue 3 + Vite + TypeScript + Tailwind + Pinia |
| Deploy | Single Docker container, `/data` + `/config` volumes |
| Source priority v1 | MangaWorld (mx) → MangaEden → MangaDex (italian-first), then MangaPark, Bato, MangaKakalot (Tier 2) |
| Content types v1 | manga + manhua + manhwa (no LN, no western comic) |
| Output | CBZ with embedded ComicInfo.xml v2.1, JPG q85, Komga/Kavita folder strategies |
| Convention | Read this file at session start, run smoke test, pick the next unchecked item |

---

## 1. Build status — step checklist

The build is organised in **17 steps**. Each step ends with a **checkpoint**
(an objective, runnable verification). Don't mark a step done until its
checkpoint passes.

Legend: `[x]` done · `[~]` in progress · `[ ]` not started · `[!]` blocked

### Phase A — Foundations

- [x] **Step 1: Project scaffolding**
  - `pyproject.toml`, `docker-compose.yml`, `docker/Dockerfile` (multi-stage), `docker/entrypoint.sh`
  - `app/main.py` (FastAPI + lifespan), `app/settings.py` (env + YAML), `app/logging_config.py`
  - `app/db/{base,session,init}.py`, `app/deps.py`
  - `app/models/orm.py` (**all 12 tables** in one file — these are reused by every later step)
  - `app/cli.py` (`python -m app.cli {health,db-init,scrape-test,metadata}`)
  - `config/{default,sources,logging}.yaml`, `.env.example`, `.gitignore`, `alembic.ini`, `migrations/env.py`
  - `tests/conftest.py`, `tests/test_smoke.py` (2 tests: health + 12 tables)
  - **Checkpoint ✓**: `pytest tests/test_smoke.py` green; `uvicorn app.main:app` returns 200 on `/api/health`.

### Phase B — Data layer

- [x] **Step 2: Alembic migrations**
  - `migrations/versions/0001_initial.py` (hand-written, 12 tables, all FKs, indexes, unique constraints)
  - `migrations/versions/0002_seed_sources.py` (insert `domain_health` rows from `config/sources.yaml`, cross-dialect `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING`)
  - `migrations/env.py` updated with `render_as_batch=True` for SQLite ALTER support
  - `app/db/init.py` enhanced to re-seed `domain_health` from YAML on every startup (INSERT OR IGNORE so runtime health-cron updates are preserved)
  - `tests/test_migrations.py` (5 tests: 12 tables, idempotency unique, seed from YAML, round-trip, indexes)
  - **Checkpoint ✓**: `pytest tests/` → **7 passed** (5 new + 2 smoke). Live `alembic upgrade head` produces 12 tables, 8 seeded domain rows, all unique constraints (incl. `uq_chapter_source_lang`), 12 indexes.

### Phase C — Scraping layer

- [x] **Step 3: Base scraper + MangaDex end-to-end**
  - `app/core/{exceptions,rate_limiter,http_client,paths,italian,hashing}.py`
  - `app/scrapers/{base,registry,domain_registry,cookies}.py`
  - `app/scrapers/mangadex.py` (REST, no auth, language priority it→en)
  - `app/services/folder_strategy.py` (4 strategies + unit tests)
  - **Checkpoint ✓**: `pytest tests/test_folder_strategy.py tests/test_scrapers_mangadex.py` → **24 passed**. Live `python -m app.cli scrape-test mangadex "death note"` returns real series from `api.mangadex.org`, fetches IT+EN chapters, and pulls real `at-home` page URLs (4 pages, cdn URLs). `aiolimiter` added to `pyproject.toml`.

- [x] **Step 4: CBZ packager + tests**
  - `app/services/{images,comicinfo,cbz}.py`
  - `tests/test_cbz.py` (deterministic ZIP, golden hash), `tests/test_comicinfo.py` (v2.1 schema)
  - **Checkpoint ✓**: `pytest tests/test_images.py tests/test_comicinfo.py tests/test_cbz.py` → **34 passed**. Full suite **65/65 green**. Highlights:
    - `convert_to_jpg` strips metadata, RGBA→white composite, quality default 85.
    - `ComicInfo` v2.1 builder: comma-joined authors per role, `Manga=YesAndRightToLeft`, `<Pages>` block with per-page geometry, XML escape safe.
    - `CbzPackager`: ZIP entries pinned to `(1980, 1, 1, 0, 0, 0)` → **golden hash test passes** (re-pack of same input = same SHA-256). `ComicInfo.xml` `ZIP_DEFLATED`, page JPEGs `ZIP_STORED`. Filenames 1-based, padded to `max(3, len(str(page_count)))`. Atomic `.tmp` write + `os.replace`. Empty-page guard.

- [x] **Step 5: MangaEden scraper** *(scope changed: MangaEden defunct)*
  - **MangaEden.com is offline as of 2026-06** (domain redirects to an unrelated site). Source is kept in `config/sources.yaml` with `enabled: false` for forward-compat.
  - **MangaWorld.mx is the de-facto Italian-first Tier 1 replacement** (same site, rebrand). Built the MangaWorld scraper ahead of schedule (was Step 6) with:
    - `app/scrapers/mangaworld.py` — HTML scraper via parsel, uses `DomainRegistry` for domain failover, `BlockedByCloudflare` on 403/503 → orchestrator falls back
    - Selectors: `h1.name.bigger` (title), `div.thumb img.rounded` (cover), label-based `Autore/Artista/Tipo/Stato/Anno di uscita/Generi/Titoli alternativi`, `div.chapters-wrapper a.chap` (chapters with Italian date), `img.page-image` (pages)
    - `app/services/language_picker.py` — `select_chapters()` Italian-first priority with library override
  - **Checkpoint ✓**: 30/30 new tests green (11 picker + 19 scraper). Full suite 95/95. Live `python -m app.cli scrape-test mangaworld "death note"` returns 2 real series from `www.mangaworld.mx`, fetches detail page (302 → slugged URL), Italian chapters, real CDN page URLs (87 pages for the oneshot).

- [ ] **Step 6: MangaWorld scraper + domain registry**
  - `app/scrapers/mangaworld.py` (HTML scrape via parsel, Cloudflare detection)
  - `app/scrapers/cloudflare.py` (Playwright/FlareSolverr dispatch)
  - `app/services/health.py` (domain health cron)
  - **Checkpoint**: domain health cron flips a fake bad domain to `healthy=False` after 3 fails.

- [x] **Step 7: Metadata providers (AniList + MangaDex)**
  - `app/metadata/{base,anilist,mangadex,googlebooks,merger,cover_cache}.py`
  - `POST /api/series/{id}/metadata/refresh` (minimal stub, fully wired in step 8)
  - **Checkpoint**: `python -m app.cli metadata "naruto"` returns a merged record. ✅ 49/49 metadata tests green; live run returns merged `Naruto` (confidence 0.876, anilist + mangadex).

### Phase D — API layer

- [x] **Step 8: Library + Series REST API**
  - `app/schemas/{library,series,chapter,job,search}.py` (Pydantic v2)
  - `app/services/{library,series,chapter}.py`
  - `app/api/{libraries,series,chapters,search,settings_api}.py`
  - `app/api/router.py`
  - **NOTE (2026-06-13)**: was mis-marked `[ ]` — the API is in fact fully
    implemented and exercised by `tests/test_api_{libraries,series,chapters,search,settings}.py`.
    `follow`/`jobs`/`covers` are deliberate 501 stubs (steps 11/12/13) and
    `backfill`/`redownload` are stubs (step 11), as designed.
  - **Checkpoint ✓**: Swagger UI at `/api/docs` → create library, search MangaDex, add series.

### Phase E — Frontend

- [x] **Step 9: Frontend skeleton + library list**
  - Scaffold `frontend/` (Vue 3 + Vite 5 + TS + Tailwind 3 + Pinia 3 + vue-router 4 + axios + lucide-vue-next)
  - `frontend/src/{main.ts,App.vue,router.ts,style.css,env.d.ts}`
  - `frontend/src/api/client.ts`, `frontend/src/types/api.ts`, `frontend/src/stores/libraries.ts`
  - `frontend/src/components/{AppShell,Sidebar,ProviderStatusBadge}.vue`
  - `frontend/src/views/{LibraryList,PlaceholderView}.vue`
  - `vite.config.ts` with proxy `/api`+`/opds` → `:8000`, `outDir='<repo>/app/web'`
  - `tests/frontend/smoke.js` (zero-dep Node smoke test)
  - **Bonus fix**: `app/api/libraries.py` route duplication (lines 108-155) — was breaking `GET /api/libraries` with `TypeError`. Removed dead copy.
  - **Checkpoint ✓**: `npm run build` populates `app/web/`; `curl http://localhost:8000/` serves the SPA (not the placeholder); `npm run dev` on :5173 sidebar shows real libraries via Vite proxy; `node tests/frontend/smoke.js` exits 0; backend `pytest` 172/172 green.

- [x] **Step 10: Search + add series flow**
  - `frontend/src/stores/{search,series}.ts` (Pinia setup stores)
  - `frontend/src/components/{SearchDialog,SeriesCard,FollowButton}.vue`
  - `frontend/src/views/{SearchPage,LibraryDetail}.vue`
  - `frontend/src/types/api.ts` extended with `SearchCandidate`, `SearchRequest`, `SearchResponse`, `SeriesListItem`, `SeriesCreate`, `SeriesExternalIdRead`
  - `frontend/src/router.ts` updated: `/library/:id` → `LibraryDetail`, `/search` → `SearchPage` (removed placeholders)
  - `frontend/src/components/AppShell.vue` updated with quick-search header button
  - **Checkpoint ✓**: end-to-end via real network — `POST /api/search` (mangadex, "one piece") returns 3 candidates, `POST /api/series` adds One Piece (id=1, status=ongoing, it language), `GET /api/series?library_id=1` shows it, `POST /follow` and `/unfollow` toggle correctly. Vite dev server proxies `/api/series` correctly. `npm run type-check` clean. `pytest tests/` 172/172 green.

- [x] **Step 14: Frontend Series detail + settings**
  - `frontend/src/components/ChapterList.vue` (+ `JobBadge.vue` already in step 12).
  - `frontend/src/views/SeriesDetail.vue` (metadata panel + follow/backfill/refresh + chapter table with CBZ download links) and `SettingsView.vue` (effective settings + provider health, read-only); `JobsView.vue` from step 12. New stores `seriesDetail.ts` + `settings.ts`; `SeriesRead`/`ChapterListItem` types; `/series/:id` + `/settings` routes swapped off the placeholder.
  - **Checkpoint ✓ (2026-06-14)**: `npm run type-check` + `build` clean. Live end-to-end against MangaDex: added a series, `GET /api/series/{id}` returns the full record the view renders, `backfill?count=2` → 2 chapters appear in `GET /api/chapters?series_id=` (with `downloaded_at`/`cbz_size`), `GET /api/chapters/{id}/file` serves the CBZ (`application/vnd.comicbook+zip`, 11.7 MB), `/api/settings` + `/api/settings/providers/health` feed SettingsView. (Cover thumbnails await the covers endpoint = Step 13; "read in Komga via OPDS" awaits Step 13.)

### Phase F — Follow scheduler + downloads

- [x] **Step 11: Follow scheduler**
  - `app/services/downloader.py` — `download_chapter()` (idempotent core), `DownloadQueue` + workers, `start/stop_download_workers` (wired in lifespan), `enqueue_download`.
  - `app/services/follow.py` — `check_series`, `backfill_series`, `check_due_series` (orchestratore lista capitoli, Italian-first, diff + enqueue).
  - `app/scheduler/jobs.py` — `AsyncIOScheduler` (memory store): `follow_check` (interval) + `cleanup_jobs` (daily). `start/stop_scheduler` wired in lifespan. (`domain_health` cron → step 15.)
  - Stub wired: `series_service.backfill_chapters` → `follow.backfill_series`; `chapter_service.redownload_chapter` → forced re-download; `POST /api/series/{id}/backfill?count=&language_priority=`.
  - Tests: `tests/test_{downloader,follow,scheduler}.py` (+ backfill API test) — full suite **183 passed**.
  - **Checkpoint ✓ (live, 2026-06-13)**: real boot → workers + scheduler (`follow_check`,`cleanup_jobs`) up; created a library, added MangaDex *Yotsuba to!*, `POST /backfill?count=1&language_priority=en` → a real **47-page CBZ** (`ComicInfo.xml` + `page001..page047.jpg`) written to `<root>/Yotsuba to!/Volume 016/...ch114...(en).cbz`; `chapters` row (47 pages, sha256, file_path) + 47 `pages` + `provider_jobs` `done`.

- [x] **Step 12: Backfill + job log**
  - Backend: `app/api/jobs.py` (`GET /api/jobs` + filters, `GET /api/jobs/{id}`, `GET /api/jobs/stream` SSE), `app/api/follow.py` (`GET /api/follow`, `POST /api/follow/{id}/check`), `app/services/job_events.py` (in-process pub/sub; workers publish running/done/error), `app/schemas/follow.py`. (No separate `backfill.py` — `follow.backfill_series` covers it.)
  - Frontend: `frontend/src/stores/jobs.ts` (`load()` + SSE `connect()`/`disconnect()`), `frontend/src/components/JobBadge.vue`, `frontend/src/views/JobsView.vue` (live table), `/jobs` route swapped off the placeholder. `npm run type-check` + `build` clean.
  - Tests: `tests/test_{job_events,api_jobs,api_follow}.py`; suite **191 passed**.
  - **Checkpoint ✓ (live, 2026-06-14)**: built SPA served by FastAPI; `GET /api/jobs/stream` streamed `running`→`done`/`error` frames in real time during a backfill (the store/JobsView consume these), `GET /api/jobs` lists them. Earlier backend run produced 3 real CBZs (`done`); a One Piece backfill surfaced a real upstream 404 as a published `error` frame (worker survived, job recorded).

### Phase G — Reader integration

- [x] **Step 13: OPDS catalog (+ covers endpoint)**
  - `app/services/opds.py` (Atom XML via `lxml.etree`, no third-party) — feed/entry builders, OpenSearch description, content-type constants.
  - `app/api/opds.py` — `/opds/v1.2/{root,libraries,libraries/{id},series/{id},followed,search,opensearch.xml}` (+ `/opds` alias); navigation feeds + per-series **acquisition** feed whose entries link to `/api/chapters/{id}/file`. Relative hrefs.
  - `app/api/covers.py` — real `GET /api/covers/series/{id}` (serves the cached cover, path-traversal guarded); used by OPDS thumbnails + frontend. (Old 501 stub + `tests/test_api_stubs.py` removed.)
  - Tests: `tests/test_opds.py` (8) — feeds parse as valid Atom, acquisition link/length correct, undownloaded chapters skipped, OpenSearch+search work, covers served/404/traversal-guarded. Suite **198 passed**.
  - **Checkpoint ✓ (live, 2026-06-14)**: navigated root → libraries → library → series feed; the acquisition href downloaded the real CBZ (`application/vnd.comicbook+zip`, 23.3 MB); `opensearch.xml` + `search?q=` found the series. (Subscribing in a real reader like Moon+/KyBook is the one remaining manual check.)

### Phase H — Reliability + deploy

- [x] **Step 15: Domain health + auto-fallback**
  - `app/services/health.py` — `check_all_domains()` pings every enabled source's domains
    (`health_check_path` from `sources.yaml`) with a **dedicated short-timeout, no-retry**
    httpx client; records via `DomainRegistry.record_success/_failure` (3 fails → `healthy=False`).
  - `app/scheduler/jobs.py` — `domain_health` interval job (`scheduler_domain_health_min`).
  - Admin endpoints (`app/api/settings_api.py`): `POST /settings/providers/health/check`
    (ping now) + `POST /settings/providers/{source}/reset` (clear failures).
  - Fixed `DomainRegistry._update`: a first-ever failure now counts as 1 (was 0 → needed 4
    fails to flip instead of 3).
  - Tests: `tests/test_health.py` (3: flip after 3 fails, `pick_domain` fallback to healthy
    alternate, recovery) + 2 settings endpoint tests + scheduler-job assertion. Suite **206 passed**.
  - **Checkpoint ✓ (live, 2026-06-14)**: `POST /api/settings/providers/health/check` pinged the
    real domains in ~26s (HTTP 200; mangadex `code=200 healthy`; CF-fronted bato/mangaworld/
    mangakakalot accrued `fail_count`); reset re-enabled a source. The 3-fail flip + alternate
    failover are covered deterministically by tests.

- [~] **Step 16: Docker multi-stage build + healthcheck** *(code ready; build/run to verify on the NAS)*
  - Multi-stage `docker/Dockerfile` finalized + fixed: node builds the SPA → `/build/app/web`,
    copied directly into the runtime image (was broken — served the placeholder); `README.md`+`LICENSE`
    now copied before `pip install .` (hatchling needs them); CMD uses `python -m uvicorn` so the
    local `app` (with `app/web`) is imported. `HEALTHCHECK` on `/api/health`; non-root user.
  - Added **`.dockerignore`** (keeps `.git`/`.venv`/`node_modules`/`dev_data`/`*.db`/`app/web`/`tests` out).
  - `docker-compose.yml` (volumes `/data`+`/config`, env w/ defaults, healthcheck, FlareSolverr sidecar commented).
  - SQLite backup cron (`BACKUP_ENABLED`) — **done** (see §9 backup entry).
  - **Checkpoint (on the NAS)**: `docker compose build && up -d` → `/api/health` 200, `/` serves the
    SPA (not the placeholder), `/data`+`/config` volumes persist, healthcheck `healthy`. `docker` is
    not available in the dev sandbox, so the build was reviewed statically here and is verified on deploy.

- [x] **Step 17: Documentation**
  - `docs/architecture.md` (components, boot order, core flows, 12-table data model, invariants),
    `docs/sources.md` (per-source table + domain health/auto-fallback + adding a source),
    `docs/comicinfo.md` (ComicInfo field-mapping + CBZ guarantees),
    `docs/api.md` (full REST + OPDS + SSE + error-format reference).
  - `CHANGELOG.md` (0.1.0 features + known limitations).
  - `README.md` extended: Documentation + Development&testing sections; accuracy fixes
    (MangaEden disabled, OPDS root `/opds/v1.2/root`, provider health in Settings).
  - All docs are anchored to the real code (route inventory, `.env.example`, `default.yaml`,
    `sources.yaml`, `comicinfo.py`/`downloader.py`, `exception_handlers.py`).
  - **Checkpoint ✓ (2026-06-14)**: README links all resolve; docs cross-links valid; smoke green.

---

## 2. Project structure — where things go

```
F:\dev\mangadownloader\
├── ROADMAP.md                    ← YOU ARE HERE
├── README.md, LICENSE, .env.example, .gitignore, pyproject.toml, alembic.ini
├── docker-compose.yml, docker/{Dockerfile,entrypoint.sh}
├── config/{default,sources,logging}.yaml
├── migrations/{env.py,script.py.mako,versions/0001_*,0002_*}
├── docs/{architecture,sources,comicinfo,api}.md        (step 17)
├── frontend/                     (Vue 3 SPA — step 9+)
│   ├── package.json, vite.config.ts, tailwind.config.js, tsconfig.json, index.html
│   └── src/{main.ts,App.vue,router.ts,style.css}
│       ├── api/{client,libraries,series,chapters,search,jobs,settings}.ts
│       ├── stores/{libraries,series,jobs,settings}.ts
│       ├── components/{AppShell,Sidebar,SeriesCard,ChapterList,
│       │               SearchDialog,FollowButton,LibraryForm,
│       │               ProviderStatusBadge,CoverImage,JobBadge}.vue
│       ├── views/{LibraryList,LibraryDetail,SeriesDetail,
│       │          SearchPage,JobsView,SettingsView}.vue
│       └── types/api.ts
├── tests/                        (pytest, asyncio_mode=auto)
│   ├── conftest.py
│   ├── test_smoke.py                              ✓ exists
│   ├── test_{cbz,comicinfo,folder_strategy,
│          scrapers_mangadex,opds}.py              (steps 3/4/13)
│
└── app/                          (FastAPI backend)
    ├── __init__.py, main.py, settings.py, logging_config.py, deps.py, cli.py
    ├── db/{__init__,base,session,init}.py
    ├── models/{__init__,orm}.py                  ✓ 12 tables in orm.py
    ├── schemas/{library,series,chapter,job,search,opds}.py
    ├── core/{exceptions,rate_limiter,http_client,paths,italian,hashing}.py
    ├── scrapers/{base,registry,domain_registry,cookies,cloudflare,
    │             mangadex,mangaeden,mangaworld,mangapark,bato,mangakakalot}.py
    ├── metadata/{base,anilist,mangadex,googlebooks,merger,cover_cache}.py
    ├── services/{library,series,chapter,follow,downloader,backfill,
    │             cbz,comicinfo,images,folder_strategy,health,
    │             language_picker,opds}.py
    ├── scheduler/jobs.py
    ├── api/{router,libraries,series,chapters,search,follow,jobs,
    │        covers,settings_api,opds}.py
    └── web/                                      (built Vue assets, gitignored)
```

---

## 3. Architectural invariants (do not break these)

These rules are baked into the design and MUST be preserved across all
steps. If a future change appears to break one, surface it before doing so.

1. **No Lua anywhere.** All scrapers are pure Python (`httpx` + `parsel` + `lxml`).
2. **No komf in the stack.** Metadata is our own (`AniListProvider` + `MangaDexProvider` + dormant `GoogleBooksProvider`).
3. **Single Docker container.** No multi-service compose unless explicitly added later. `/data` and `/config` are the only persistent volumes.
4. **Italian-first.** For any series with both `it` and `en` translations, `it` wins. `library.italian_priority` is a hard default.
5. **Idempotency by `(source_provider, source_id, language)`.** A chapter downloaded twice is the same DB row. The DB unique constraint enforces this; the orchestrator also pre-checks.
6. **ComicInfo.xml v2.1 is mandatory in every CBZ.** Schema reference: <https://anansi-project.github.io/docs/comicinfo/schemas/v2.1>. `ComicInfoBuilder` is the single source — never hand-write XML.
7. **Zero-padded page names** (`page001.jpg`, …) width = `max(3, len(str(pages_count)))`. Page order inside the CBZ is lexicographic — zero-padding is what makes that work.
8. **Deterministic ZIPs**: every entry is timestamped `(1980, 1, 1, 0, 0, 0)` so rebuilds are byte-identical (good for dedup and checksums).
9. **Domain registry over hardcoded URLs.** Any new source goes in `config/sources.yaml`, not in code. `DomainRegistry` is the only thing that knows which domain is healthy.
10. **Italian sources are Tier 1.** When ordering providers, the library default is `["mangaworld", "mangaeden", "mangadex"]`. The series may override via `series.source_priority`.
11. **Content types**: v1 = `manga | manhua | manhwa` only. Reject `novel | comic | webtoon` at the API boundary with a 400. (Type `webtoon` is reserved for v2; if you find yourself adding it, ask first.)
12. **DB unique constraints are real**, not advisory. If a future migration drops one, it must be re-added or replaced.
13. **The 12-table schema is fixed.** Adding columns is fine, splitting tables needs a discussion.

---

## 4. Critical file map (load-bearing)

If a file is listed here, treat changes to it as architecture-level.

| File | Why it's critical |
|---|---|
| `pyproject.toml` | Dep graph; lockfile-equivalent. `pip install -e ".[dev]"` must work. |
| `docker/Dockerfile` | Multi-stage. The runtime stage is correct as of step 1; the frontend stage becomes real in step 16. |
| `docker-compose.yml` | Single service + optional FlareSolverr sidecar. Don't add sidecars without good reason. |
| `app/main.py` | Lifespan ordering matters: settings → logging → dirs → DB → workers → scheduler. |
| `app/settings.py` | Single source of truth for env vars. Don't read `os.environ` elsewhere. |
| `app/models/orm.py` | All 12 tables. |
| `migrations/versions/0001_initial.py` | Schema-as-code. Every column starts here. |
| `app/scrapers/base.py` | `BaseScraper` + 3 dataclasses. Every concrete scraper implements this contract. |
| `app/scrapers/domain_registry.py` | Source-of-truth for "which domain of which source is healthy now". |
| `app/services/cbz.py` | Deterministic ZIP. One day you'll be glad it's deterministic. |
| `app/services/comicinfo.py` | v2.1 template. Single source for metadata XML. |
| `app/services/folder_strategy.py` | The 4 strategies. Komga and Kavita both have opinions; ours is the one we ship. |
| `app/services/downloader.py` | `DownloadQueue` + workers. Idempotency lives here. |
| `app/services/follow.py` | `FollowScheduler`. Reads `series.source_priority` and `library.providers`. |
| `app/services/opds.py` | Atom XML via `lxml.etree`. No third-party. |
| `app/scheduler/jobs.py` | APScheduler. Boot order: queues first, scheduler second. |
| `app/api/opds.py` | OPDS routes. Readers (Moon+, KyBook, Komga, Kavita) consume these. |
| `config/sources.yaml` | Domain registry + per-source config. Edit this, not code. |

---

## 5. Conventions

### Python

- **Target**: Python 3.12+. We tested on 3.12.10 and 3.14.3.
- **Style**: ruff (line 110, py312, rule sets E/F/I/N/W/UP/B/SIM/RUF/ASYNC/TCH).
- **Types**: full type hints; mypy strict mode in `pyproject.toml`. Pydantic v2 for all I/O models.
- **Async**: `httpx.AsyncClient`, `asyncio.Queue`, `aiosqlite` for DB. Never `requests`. Never blocking I/O in the request path.
- **Logging**: `from app.logging_config import get_logger; log = get_logger(__name__)`. structlog.
- **Errors**: domain exceptions in `app/core/exceptions.py` (e.g. `BlockedByCloudflare`, `SourceUnavailable`, `ChapterNotFound`). FastAPI handlers convert them to HTTP responses at the boundary.

### DB

- **Migrations**: Alembic. New schema changes → new migration, never edit `0001_initial.py` after merge.
- **Timestamps**: always `DateTime(timezone=True)`, UTC. Use `_utcnow()` from `app/models/orm.py`.
- **JSON columns**: `JSON` type (SQLite stores as TEXT). Lists/dicts only; never store `None` — use a default of `[]` or `{}`.
- **Soft delete**: `deleted: bool` on `libraries` and `series`. Hard delete only on cascade child rows.
- **Cascade**: `ondelete="CASCADE"` on all parent→child FKs. Use `passive_deletes=True` on relationships to let the DB do the work.

### Frontend (once it exists, step 9+)

- **TypeScript strict mode**. No `any` outside API boundary shims.
- **Composition API** with `<script setup>`. No Options API.
- **State**: Pinia. No Vuex, no composables-as-stores.
- **API calls**: axios via `frontend/src/api/client.ts`. Don't instantiate axios per component.
- **Styling**: Tailwind utility-first. Component-scoped styles only when Tailwind can't express it.
- **Icons**: `lucide-vue-next`. No emoji icons, no inline SVGs.
- **Toasts**: `vue-sonner`. Don't roll your own.

### Git / commit hygiene (when the repo is initialised)

- One commit per step. Message: `Step N: <title>`.
- Each commit leaves the project in a runnable state. If a checkpoint isn't green, the commit doesn't happen.
- The `app/web/` directory is gitignored; never commit built assets.

---

## 6. Run-the-project cheat sheet

> Replace `& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe"` with `python` (or `py`) once your PATH is set up. The full path is used here only because Windows' default `python` alias points to the Microsoft Store stub.

### Local dev (Windows)

```powershell
# One-time setup.
cd F:\dev\mangadownloader
& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -e ".[dev]"

# Run tests.
& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m pytest -v

# Apply migrations.
& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m alembic upgrade head

# Run the API.
$env:DATA_DIR = "F:\dev\mangadownloader\dev_data"
$env:CONFIG_DIR = "F:\dev\mangadownloader\dev_config"
& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn app.main:app --reload --port 8000
```

### Local dev (Linux / macOS / WSL)

```bash
cd /f/dev/mangadownloader   # or wherever it lives
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
DATA_DIR=./dev_data CONFIG_DIR=./dev_config uvicorn app.main:app --reload
```

### Docker

```bash
cd F:\dev\mangadownloader
cp .env.example .env       # edit if you want
docker compose up -d --build
docker compose logs -f mangasama
open http://localhost:8000
```

### CLI helpers

```powershell
& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m app.cli health
& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m app.cli db-init
# Step 3+:
& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m app.cli scrape-test mangadex "death note"
# Step 7+:
& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m app.cli metadata "naruto"
```

---

## 7. Session-start checklist for any AI assistant

When a new session opens, the AI MUST do the following before doing anything else:

1. **Read this file** (`ROADMAP.md`) in full. Confirm the build status table.
2. **Read the plan** at `.claude/plans/g-dev-mangadownloader-voglio-creare-floating-hartmanis.md` for the architectural detail.
3. **Identify the next step** as the first `[ ]` (or `[~]`) item in the build status.
4. **Run the smoke test** to confirm the project is healthy:
   `& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_smoke.py -v`
5. **Read the critical files** for the next step (see the file map in §4).
6. **State the plan** for the next step in plain text before writing any code, and **update this file's checklist** as the work progresses.
7. **Never assume** a step is done if its checkpoint is not green. If unsure, run the checkpoint.

If the user asks for something outside this plan, add it to §10 ("Out-of-plan work") rather than silently expanding scope.

---

## 8. Checkpoint protocol — what "done" means for each step

A step is "done" when:

1. All code for that step is written.
2. The checkpoint command (see step description) passes.
3. The corresponding line in §1 is changed from `[ ]` to `[x]`.
4. If the step touches a public API or DB schema, `git log -p` shows the change is minimal and consistent with the rest.

If a step is partially done, leave it as `[~]` and add a note in §9.

---

## 9. Open issues / in-flight notes

> Append-only log. Don't delete past entries; strike through resolved ones.

- **2026-06-13 — code-review fixes (no new step):**
  - `app/services/series.py` `refresh_metadata` built the response via
    `SeriesRead.model_validate(s)`, which raised `ValidationError` whenever
    genres/tags were present (ORM exposes rows, schema wants `list[str]`).
    Since `add_series` defaults `run_metadata_refresh=True` and swallows
    exceptions, metadata refresh failed *silently* on every real add.
    Fixed via a shared `to_series_read()` mapper + flush/reload; `_to_read`
    in `app/api/series.py` now delegates to it. Regression test added:
    `tests/test_api_series.py::test_metadata_refresh_with_genres_and_tags`.
  - `list_series` had a dead `q` filter (`... if False else ...`,
    non-existent `cast_to_string()`) → searched only `title`. Now searches
    `title` + `alt_titles` via `cast(alt_titles, String)`.
  - `list_series` did not exclude soft-deleted rows → added
    `Series.deleted.is_(False)`.
  - `_apply_merged_to_series` wrote `series.metadata = ...` (SQLAlchemy
    reserved attr, no such column) and had a dead `country` branch — both
    removed (publisher/country have no column in v1).
- **2026-06-13 — Step 11 core (download engine):**
  - Added `app/services/downloader.py` (`download_chapter` idempotent core +
    `DownloadQueue`/workers) and `app/services/follow.py` (`check_series`,
    `backfill_series`, `check_due_series`). Wired the `backfill`/`redownload`
    stubs to the real engine. Tests added; suite **179 passed**.
  - **Still TODO for Step 11**: `app/scheduler/jobs.py` (APScheduler) to call
    `check_due_series` periodically, and the `follow`/`jobs` REST endpoints
    (still 501 stubs → Step 12). The download workers themselves DO start at
    real boot via the existing lifespan block.
- **2026-06-13 — Step 11 closed (APScheduler + live checkpoint):**
  - Added `app/scheduler/jobs.py` (`AsyncIOScheduler`, memory store, jobs
    `follow_check` + `cleanup_jobs`), wired into the lifespan. Added
    `count`/`language_priority` query params to `POST /api/series/{id}/backfill`.
  - **Live verification passed** against real MangaDex (see Step 11 checkpoint):
    a 47-page CBZ was downloaded end-to-end and all DB rows written. Suite **183 passed**.
  - Remaining for the wider feature set: `follow`/`jobs` REST + SSE (Step 12),
    `domain_health` cron (Step 15). The `MangaWorld` path (Step 6 cron/Cloudflare)
    is still open too.
- **2026-06-14 — Step 12 backend (jobs/SSE/follow API) + concurrency fix:**
  - Added `app/services/job_events.py` (SSE pub/sub), real `app/api/jobs.py`
    (list/get/stream) and `app/api/follow.py` (list/check), `app/schemas/follow.py`,
    `follow.list_followed_status`. Workers publish job events. Suite **191 passed**.
  - **Concurrency bug found during live verify & fixed** (was in the Step 11
    engine): the download worker held one SQLite write transaction for the whole
    network download (job-insert → … → commit), so a 2nd concurrent worker hit
    `database is locked` on a `flush()` *outside* the try → the worker died
    silently (no job row, no error log) → `backfill?count=N` reported N but
    downloaded fewer. Fixes:
    - `app/db/base.py`: per-connection `PRAGMA journal_mode=WAL` + `busy_timeout=30000` + `synchronous=NORMAL`.
    - `app/services/downloader.py`: `_run_task` now uses **short transactions**
      (create job → commit; download with no open write txn; mark job → commit);
      `download_chapter` does all DB writes *after* the network fetch; the worker
      loop guards every task so a failure can never kill the worker.
    - Re-verified live: `backfill?count=3` → `download.ok=3, crashed=0, locked=0`,
      3 jobs `done`, 3 CBZs.
  - **Known follow-up (not a regression)**: sources list multiple uploads per
    chapter *number* (different `external_id`); selection currently treats each as
    a distinct chapter, so `count`-based backfill can fetch several scanlations of
    the same number. `language_picker`/selection should dedupe by `(number, language)`
    keeping the best upload — a Step-11/scraper-selection improvement.
  - **Known edge (pre-existing)**: `series_external_ids` is globally unique on
    `(provider, external_id)`, so adding the *same* source series to a *second*
    library leaves the 2nd series with no provider mapping → `backfill` then raises
    an unmapped `LookupError` (HTTP 500). Should be a clean 4xx and/or the schema
    should allow per-library mappings — revisit when multi-library sharing matters.
  - **Still TODO for Step 12**: frontend `JobsView`/`JobBadge`/`useJobsStore`.
- **2026-06-14 — Step 12 closed (frontend JobsView + live SSE):**
  - Added `frontend/src/stores/jobs.ts` (history `load()` + `EventSource` live merge),
    `frontend/src/components/JobBadge.vue`, `frontend/src/views/JobsView.vue`; `/jobs`
    route now renders the real view. `JobEvent`/`JobRead` types added.
  - Verified live on the prod same-origin path: SPA served by FastAPI, SSE frames
    (`running`→`done`/`error`) flow to the store. `npm run type-check` + `build` clean;
    backend suite still **191 passed**.
- **2026-06-14 — Step 14 (frontend Series detail + Settings):**
  - `frontend/src/views/{SeriesDetail,SettingsView}.vue`, `components/ChapterList.vue`,
    `stores/{seriesDetail,settings}.ts`, `SeriesRead`/`ChapterListItem` types; `/series/:id`
    and `/settings` now render real views. `PlaceholderView.vue` is no longer routed (kept in repo).
  - Verified live: series detail → backfill → chapters list with working CBZ download links;
    settings + provider health render. type-check + build clean; backend untouched (**191 passed**).
  - Out of scope (noted): cover thumbnails need the covers endpoint (Step 13); SettingsView is
    read-only (the `PATCH /api/settings` allow-list edit is a future nicety).
- **2026-06-14 — Step 13 (OPDS 1.2 catalog + covers):**
  - `app/services/opds.py` + `app/api/opds.py` (navigation + acquisition feeds, OpenSearch,
    relative hrefs to `/api/chapters/{id}/file`); `app/api/covers.py` now serves cached covers
    (traversal-guarded). Removed the covers 501 stub and `tests/test_api_stubs.py`.
  - Verified live: full feed navigation + CBZ download via the acquisition link + search.
    `tests/test_opds.py` (8) added; suite **198 passed**. The covers endpoint also unblocks the
    cover thumbnails the frontend (`SeriesCard`/`SeriesDetail`) can now show.
  - **Known follow-up**: the frontend doesn't yet render `<img src="/api/covers/series/{id}">`
    (small enhancement, deferred).
- **2026-06-14 — Consolidation / bugfix round (no new step):**
  - **Fixed** `app/services/library.py:library_stats`: the chapter join went
    `Series.id == Chapter.volume_id` (wrong); now joins through `Volume`
    (`Volume.id == Chapter.volume_id` → `Series.id == Volume.series_id`), so
    `chapter_count`/`downloaded_chapter_count`/`total_cbz_bytes` are correct.
    Regression test `test_library_stats_with_chapters`.
  - **Italian-first dedup**: `follow._list_selected` now keeps **one chapter per
    `number`** (first wins after the italian-first ordering), so a number present
    in it+en — or in multiple scanlation uploads — is downloaded once, in Italian.
    Enforces invariant #4. Test `test_backfill_dedupes_by_number`.
  - **Cleaner error**: `follow._pick_provider` raises `ConfigError` (→ HTTP 400)
    instead of an unmapped `LookupError` (→ 500) when a series has no usable
    provider. Test `test_backfill_no_provider_returns_400`. (The underlying
    `series_external_ids` global-unique limitation across libraries remains.)
  - **Frontend covers**: `SeriesCard.vue` + `SeriesDetail.vue` now render the cover
    via `/api/covers/series/{id}` with a graceful `@error` fallback.
  - Suite **201 passed**; `npm run type-check` + `build` clean.

---

- **2026-06-14 — Step 15 (domain health + auto-fallback):**
  - Added `app/services/health.py` (short-timeout no-retry liveness probe), the
    `domain_health` scheduler job, and admin endpoints
    (`POST /api/settings/providers/health/check` + `.../{source}/reset`).
  - Fixed `DomainRegistry._update` first-failure-counts-as-1 bug. Suite **206 passed**;
    live health check verified (~26s, fast — earlier the shared retrying client took >90s,
    which is why the probe now uses its own short-timeout client).
  - This also covers the **domain-health cron** half of Step 6 — of Step 6 only the
    **Cloudflare handler** (`app/scrapers/cloudflare.py` + dispatch) remains.
- **2026-06-14 — Step 17 (documentation):**
  - Added `docs/{architecture,api,sources,comicinfo}.md` + `CHANGELOG.md`; extended `README.md`
    (Documentation + Development&testing, accuracy fixes). All anchored to the real code; links
    verified; smoke green. Remaining build steps: **Step 16 (Docker)** and the **Cloudflare
    handler** (residual Step 6) — both hard to verify in this sandbox.

---

- **2026-06-14 — Version control + Auth:**
  - **Git initialized** and pushed to a **private** GitHub repo
    `iCosiSenpai/mangasama` (branch `main`). `.gitignore` extended (`dev_data/`, `dev_config/`);
    verified no `.env`/`*.db`/`app/web`/`node_modules` committed. (Local git identity set in-repo.)
  - **Auth implemented** (was: flags only, unenforced): optional single-admin **HTTP Basic** gate
    — `app/core/auth.py` + a middleware in `app/main.py` guarding `/api` and `/opds` when
    `AUTH_ENABLED=true` (`/api/health` + SPA static stay public; `401` + `WWW-Authenticate`).
    Frontend: `stores/auth.ts`, a 401→login interceptor, `LoginView.vue` + `/login`. Tests:
    `tests/test_auth.py` (6). Suite **212 passed**; frontend type-check + build clean.
  - Remaining: Docker (Step 16, on the NAS), Cloudflare handler, library-from-UI, SQLite backup,
    `series_external_ids` per-library.
- **2026-06-14 — Library management from the UI:**
  - `frontend/src/components/LibraryForm.vue` (create + edit drawer: name, type, root_path,
    folder strategy, providers multi-select from known scrapers, italian priority, follow
    interval, jpg quality). Wired into `LibraryList` (create) and `LibraryDetail` (Edit + Delete).
    Store gained `create`/`update`/`remove` + forced re-fetch. type-check + build clean; live
    create→edit→delete verified on the prod path. Closes the "library only via Swagger" gap.

---

- **2026-06-14 — SQLite backup:**
  - `app/services/backup.py` — WAL-safe online snapshot (`sqlite3.Connection.backup`) to
    `<config>/backups/mangasama-<ts>.db` + age-based pruning (`backup_retention_days`).
    Daily scheduler job `backup` registered only when `BACKUP_ENABLED`; manual
    `POST /api/settings/backup` (always available) + "Backup ora" button in Settings.
  - Tests: `tests/test_backup.py` (3) + scheduler/settings extensions; live `POST` produced a
    valid 13-table snapshot. Suite green; frontend type-check + build clean.

---

- **2026-06-14 — UI toasts (vue-sonner):**
  - Added `vue-sonner` (dep), mounted `<Toaster>` in `App.vue`, replaced the `console.error/info`
    placeholders with `toast.success/error` across follow/add/backfill/metadata/library-CRUD/backup.
    type-check + build clean (sonner CSS bundled). Frontend-only; backend untouched (217 tests).

---

- **2026-06-14 — CI (GitHub Actions):**
  - `.github/workflows/ci.yml` runs on push to `main` + PRs: **backend** job (`pip install -e ".[dev]"`
    + `pytest`) and **frontend** job (`npm ci` + type-check + build); ruff advisory (legacy nits).
    Verified green end-to-end on Actions (both jobs `success`) via `gh run watch`.

---

- **2026-06-14 — Frontend unit tests (vitest):**
  - Added `vitest` + `@vue/test-utils` + `jsdom` (dev) and `vitest.config.ts` (jsdom, reuses the
    vite `@` alias); specs excluded from `tsconfig` so build/type-check stay decoupled. Specs:
    `stores/libraries.spec.ts`, `components/JobBadge.spec.ts`, `components/FollowButton.spec.ts`
    (10 tests). Added `npm run test` to the CI frontend job. All green locally + in CI.

---

- **2026-06-14 — Ruff cleanup + onboarding + CI hardening:**
  - `ruff check app tests` is now **clean** and a **blocking** CI gate. Auto-fixed safe rules
    (UP045/UP017/UP035/UP037/F401/I001/RUF022/RUF019/RUF100); fixed a real bug `base.py`
    `_domain` used `lstrip("www.")` (strips chars, not the prefix) → `removeprefix`; plus F841,
    E741, SIM101/105/108. Deliberately ignored `TC001-3` (Pydantic/SQLAlchemy runtime
    annotations + direct-import convention), `N818` (intentional exception names), `ASYNC240`
    (cheap `Path.stat`), `RUF012` (ORM/dataclass mutable defaults) — see `pyproject.toml`.
  - Rewrote `CLAUDE.md` (OS-agnostic, deploy-oriented, removed dead plan-file refs), refreshed
    the ROADMAP footer, added a README "Deploy on a NAS" section.
  - **CI npm fix**: `package-lock.json` is lockfileVersion 3 (npm 11); node 20 ships npm 10
    whose `npm ci` reported it out of sync once vitest pulled a second esbuild → the frontend
    job now runs `npm install -g npm@11` before `npm ci`. (Note: an earlier "CI green" report was
    mis-attributed to a previous run; the vitest run had actually failed here — now genuinely
    green, verified by run id: both jobs `success`.) **Use npm 11 when regenerating the lock.**

---

## 10. Out-of-plan work (future requests, not in the 17 steps)

Track here anything the user asks for that wasn't in the original plan.

- _(empty)_

---

## 11. References

- **Full plan**: `.claude/plans/g-dev-mangadownloader-voglio-creare-floating-hartmanis.md`
- **ComicInfo v2.1 schema**: <https://anansi-project.github.io/docs/comicinfo/schemas/v2.1>
- **MangaDex API docs**: <https://api.mangadex.org/docs/>
- **AniList GraphQL**: <https://graphql.anilist.co> (also <https://docs.anilist.co>)
- **OPDS 1.2 spec**: <https://specs.opds.io/opds-1.2.html>
- **Komga folder conventions**: <https://komga.org/docs/>
- **Kavita naming guide**: <https://wiki.kavitareader.com/guides/naming/>

---

*Last updated: 2026-06-14 — feature-complete. Build steps 1–17 done, plus optional HTTP Basic
auth, SQLite backups, library management from the UI, toasts, and GitHub Actions CI (pytest +
frontend type-check/test/build, green). 217 backend tests + 10 frontend unit tests; `ruff check
app tests` clean. On GitHub at `iCosiSenpai/mangasama` (private). Remaining: Docker build/run
verified on the NAS at deploy time, Cloudflare solver, `series_external_ids` per-library.
See §9 for the full history.*
