# MangaSama

> Personal archival manga downloader. Italian-first sources, multi-library, follow scheduler, CBZ output, OPDS catalog. Single Docker container.

**MangaSama** lets you **follow** any manga, manhua, or manhwa and automatically downloads new chapters into your NAS/PC/Mac folders, organised in Komga/Kavita-compatible folder structures with embedded `ComicInfo.xml` metadata. It also serves an **OPDS 1.2 catalog** so e-readers and reader apps (Moon+ Reader, KyBook, Komga, Kavita) can browse and download directly.

**Features**

- 🌍 **Multi-source, Italian-first**: **MangaWorld** (IT) + **MangaDex** (IT scanlations) as active scrapers; Tier-2 sources (Bato, MangaKakalot, MangaPark) are registered in config for future scrapers. See [docs/sources.md](docs/sources.md).
- ⭐ **Follow / Like** series and have new chapters auto-downloaded.
- 📚 **Multi-library**: separate libraries for different content types or organisations; each library has its own root path, source priority, and folder strategy.
- 📦 **CBZ with ComicInfo.xml v2.1** embedded — works with Komga, Kavita, YACReader, Moon+ Reader.
- 🗂 **Komga/Kavita-compatible folder strategies**: `series_volume_chapter`, `series_volume`, `chapter_flat`, `onefile_per_volume`.
- 📖 **OPDS 1.2** catalog for e-readers.
- 🛡 **Anti-bot aware**: optional Playwright or FlareSolverr sidecar, per-domain cookie cache, graceful fallback to the next source.
- 🇮🇹 **Italian priority**: when a series has both Italian and English translations, Italian wins.
- 🐳 **Single Docker container**, `/data` and `/config` volumes — drop in your NAS, Synology, Unraid, or Raspberry Pi.

**Non-goals (v1)**: light novels, western comics, multi-user accounts, public service scraping. MangaSama is for personal archival.

## Quickstart (Docker)

```bash
git clone https://github.com/iCosiSenpai/mangasama.git
cd mangasama
cp .env.example .env
docker compose up -d
open http://localhost:8000
```

That's it. The first start runs Alembic migrations automatically and creates the SQLite DB at `/data/mangasama.db`. Open the UI, create a library, search for a series, click **Follow**.

### Deploy on a NAS / self-host

Copy (or `git clone`) the repo onto the host and run `docker compose up -d` — the multi-stage
build compiles the Vue SPA and the Python backend into one image, runs migrations on boot, and
serves the UI + API + OPDS on `:8000`. Two volumes persist your data:

- **`/data`** — SQLite DB and the downloaded library folders (point libraries' `root_path` here, e.g. `/data/manga_it`).
- **`/config`** — YAML config, cookie cache, and backups.

Useful env (in `.env`): `AUTH_ENABLED=true` + `ADMIN_PASSWORD=…` (HTTP Basic gate over the API/OPDS),
`BACKUP_ENABLED=true` (daily WAL-safe SQLite backup to `/config/backups`), `CLOUDFLARE_SOLVER`.
The container exposes a `HEALTHCHECK` on `GET /api/health`. See [docs/architecture.md](docs/architecture.md).

## Quickstart (local dev)

```bash
git clone https://github.com/iCosiSenpai/mangasama.git
cd mangasama
python -m venv .venv && . .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
cd frontend && npm install && npm run build && cd ..
alembic upgrade head
uvicorn app.main:app --reload
```

Open http://localhost:8000.

## Architecture

```
Browser ──► FastAPI (Vue 3 SPA served from /)
             │
             ├── /api/*        (REST: libraries, series, chapters, jobs, settings)
             ├── /opds/v1.2/*  (Atom XML for e-readers)
             │
             ├── APScheduler ─── follow_check, domain_health, cleanup
             ├── DownloadQueue ── N asyncio workers ─► CbzPackager
             │
             ├── Scrapers:  MangaDex, MangaWorld (+ Bato/MangaKakalot/MangaPark planned)
             ├── Metadata:  AniList (GraphQL), MangaDex, GoogleBooks (dormant)
             └── SQLite (libraries, series, volumes, chapters, pages, jobs, ...)
```

See [docs/architecture.md](docs/architecture.md) for the data flow diagram.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `DATA_DIR` | `/data` | SQLite DB + library folders |
| `CONFIG_DIR` | `/config` | YAML configs, cookie cache |
| `AUTH_ENABLED` | `false` | Set to `true` and set `ADMIN_PASSWORD` to gate the API/OPDS |
| `ADMIN_PASSWORD` | _(empty)_ | Single-admin HTTP Basic password (required when auth is on) |
| `AUTH_MAX_FAILURES` | `10` | Failed auth attempts from one client before a temporary lockout |
| `AUTH_LOCKOUT_SECONDS` | `60` | How long a client is locked out (HTTP 429) after too many failures |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allowed origins (dev only; prod is same-origin) |
| `FORWARDED_ALLOW_IPS` | `*` | Client IPs trusted for `X-Forwarded-*`; tighten to your proxy CIDR in prod |
| `CLOUDFLARE_SOLVER` | unset | `playwright` or `flaresolverr` |
| `SCRAPER_MANGAPARK_ENABLED` | `false` | Tier-2 opt-in |

See [`.env.example`](.env.example) for the full list of environment variables, and
`config/default.yaml` / `config/sources.yaml` for YAML defaults and the source registry.

### Security

MangaSama is designed for a **single user on a trusted LAN/NAS**, but ships several hardening
measures:

- **Security headers** on every response (`Content-Security-Policy`, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`). The strict CSP is
  skipped only for the interactive API docs.
- **Optional HTTP Basic gate** over `/api` and `/opds` (`AUTH_ENABLED` + `ADMIN_PASSWORD`), with a
  constant-time password check and an in-memory **brute-force lockout** (`AUTH_MAX_FAILURES` /
  `AUTH_LOCKOUT_SECONDS`).
- **No secret leakage**: `GET /api/settings` redacts the database path; unexpected errors return a
  generic JSON 500 (the real cause is logged server-side only).
- **Configurable CORS / proxy trust** via `CORS_ORIGINS` and `FORWARDED_ALLOW_IPS`.
- **Dependency hygiene**: Dependabot (`.github/dependabot.yml`) plus an advisory `pip-audit` /
  `npm audit` job in CI.

If you expose MangaSama beyond a trusted network, **always** enable auth, put it behind a TLS
reverse proxy, and restrict `FORWARDED_ALLOW_IPS` to that proxy.

## Documentation

- [docs/architecture.md](docs/architecture.md) — components, boot order, core flows, data model, invariants.
- [docs/api.md](docs/api.md) — REST + OPDS reference, SSE, error format (also: Swagger at `/api/docs`).
- [docs/sources.md](docs/sources.md) — per-source notes, domain health/auto-fallback, adding a source.
- [docs/comicinfo.md](docs/comicinfo.md) — ComicInfo.xml field mapping + CBZ guarantees.
- [CHANGELOG.md](CHANGELOG.md) — release notes & known limitations.

The OPDS catalog root is `http://localhost:8000/opds/v1.2/root`. Provider/domain health is shown
in the **Settings** view.

## Development & testing

```bash
pip install -e ".[dev]"
pytest -q                            # backend test suite
pytest -q --cov=app --cov-report=term-missing  # with coverage
ruff check app tests                 # lint (CI gate)
mypy app                             # static types (advisory)
cd frontend
npm install
npm run type-check && npm run test && npm run build  # type-check, vitest, build SPA into app/web/
node ../tests/frontend/smoke.js      # backend must be running on :8000
```

CI (GitHub Actions, `.github/workflows/ci.yml`) runs on every push to `main` and on pull requests:

- **Backend**: `ruff` (gate), `mypy` (advisory), `pytest` with coverage.
- **Frontend**: `type-check`, `vitest`, and `build`.
- **Security audit** (advisory, non-blocking): `pip-audit` + `npm audit`.

## Project layout

```
mangasama/
├── app/                  # Python backend
│   ├── api/              # FastAPI routers
│   ├── core/             # rate limiter, http client, paths
│   ├── db/               # session + init
│   ├── models/           # SQLAlchemy 2.0 ORM
│   ├── schemas/          # Pydantic v2
│   ├── scrapers/         # Base + MangaDex + MangaWorld (tier-2 planned)
│   ├── metadata/         # AniList, MangaDex, GoogleBooks
│   ├── services/         # CBZ builder, follow, OPDS, ...
│   ├── scheduler/        # APScheduler jobs
│   └── web/              # built Vue assets (gitignored)
├── frontend/             # Vue 3 + Vite + Tailwind
├── config/               # default.yaml, sources.yaml, logging.yaml
├── migrations/           # Alembic
├── docker/               # Dockerfile + entrypoint
└── tests/                # pytest
```

## Roadmap

**v0.1.0** ships: MangaDex + MangaWorld scrapers, FlareSolverr Cloudflare bypass, AniList + MangaDex metadata, follow scheduler, CBZ+ComicInfo, OPDS, Vue 3 UI, Docker with auto-seeded `/config`.

**Planned**: Bato + MangaKakalot + MangaPark scrapers, Playwright CF solver, light novels (Google Books), multi-user auth.

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

MangaSama is for personal archival of legally-obtained content. Respect the rights of scanlators and publishers. Do not use this tool to redistribute copyrighted material.
