# MangaSama

> Your personal manga library that downloads itself. Follow a series once, and MangaSama keeps
> grabbing new chapters into tidy folders on your NAS or computer — Italian-first, ready for Komga,
> Kavita, and any OPDS e-reader. All in **one Docker container**.

MangaSama lets you **follow** manga, manhua, and manhwa and automatically downloads new chapters as
**CBZ files** (with embedded `ComicInfo.xml` metadata) into folders that Komga, Kavita, YACReader,
and Moon+ Reader understand. It also serves an **OPDS 1.2 catalog**, so reader apps can browse and
download straight from MangaSama.

It runs anywhere Docker runs: **Synology / QNAP / Unraid NAS**, or a **Windows / macOS / Linux**
desktop.

---

## What you get

- 🌍 **Italian-first, multi-source** — MangaWorld (IT) + MangaDex; when a chapter exists in both
  Italian and English, Italian wins.
- ⭐ **Follow & forget** — new chapters are downloaded automatically on a schedule.
- 📚 **Multiple libraries** — separate folders/rules for different collections.
- 📦 **CBZ + ComicInfo.xml** — clean files for Komga, Kavita, YACReader, Moon+ Reader.
- 📖 **OPDS 1.2 catalog** — read on your e-reader / phone app.
- 🖥 **Simple web UI** — search, add, follow, and watch downloads live.
- 🐳 **One container, two folders** (`/data`, `/config`) — drop it on your NAS and go.

> **Not included (v1):** light novels, western comics, multi-user accounts. MangaSama is for
> personal archiving of content you’re allowed to download.

---

## Quick start (Docker Compose)

You only need **Docker** with the **Compose** plugin. The image is published to GitHub Container
Registry, so there's nothing to clone. Create an empty folder, and save this as `docker-compose.yml`:

```yaml
services:
  mangasama:
    image: ghcr.io/icosisenpai/mangasama:latest
    container_name: mangasama
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - mangasama-data:/data        # database + your downloaded CBZ library
      - mangasama-config:/config    # config, cookie cache, backups
    environment:
      - TZ=Europe/Rome
      # --- Optional: require a login (recommended if others can reach this host) ---
      # - AUTH_ENABLED=true
      # - ADMIN_PASSWORD=change-me
      # --- Optional: daily database backup to /config/backups ---
      # - BACKUP_ENABLED=true
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=5).status==200 else 1)"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 30s

volumes:
  mangasama-data:
  mangasama-config:
```

Then start it:

```bash
docker compose up -d
```

Open **<http://localhost:8000>** (or `http://<NAS-IP>:8000` from another device) — create a library,
search a series, and click **Follow**.

### Everyday commands

```bash
docker compose logs -f                          # follow the logs
docker compose pull && docker compose up -d     # update to the latest version
docker compose restart                          # restart
docker compose stop                             # stop (keeps everything)
docker compose down                             # remove the container (data volumes are kept)
```

### Make your library visible on disk (optional)

By default files live in Docker-managed volumes (`mangasama-data` = DB + your CBZ library,
`mangasama-config` = config/cookies/backups). To keep the downloaded manga in a **normal folder you
can browse** (e.g. a Komga/Kavita share), replace the `volumes:` block with bind mounts:

```yaml
    volumes:
      - /volume1/manga:/data                 # host folder : container (Synology example)
      - /volume1/docker/mangasama:/config
```

Windows: `C:/Users/you/Manga:/data` · macOS: `/Users/you/Manga:/data`. Then set each library's
**Root path** to a subfolder of `/data` (e.g. `/data/manga_it`) in the UI, and the CBZ files appear
right in that host folder. Make sure the host folder is writable by user/group ID **1000** (the
container's user).

### Build from source (optional)

If you'd rather build the image yourself instead of pulling it:

```bash
git clone https://github.com/iCosiSenpai/mangasama.git && cd mangasama
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

---

## Platform notes

### Synology (DSM 7 — Container Manager)
1. Create a folder on the NAS (e.g. `/volume1/docker/mangasama`) and upload `docker-compose.yml`
   into it with File Station.
2. **Container Manager ▸ Project ▸ Create**, point it at that folder, and start — it pulls the image.
3. Open `http://<NAS-IP>:8000`. For a visible library folder, use the bind-mount override above.

### QNAP (Container Station)
Container Station ▸ **Applications ▸ Create**, paste the contents of `docker-compose.yml` (and your
override), then start — it pulls the image. Browse to `http://<NAS-IP>:8000`.

### Unraid
Use the **Compose Manager** plugin: add a new stack, paste `docker-compose.yml`, and start. Map the
volumes to your array shares (e.g. `/mnt/user/manga:/data`) for visible files.

> The published image is **multi-arch** (`linux/amd64` + `linux/arm64`), so it runs on Intel/AMD
> NAS and desktops as well as ARM boards (e.g. ARM Synology models, Raspberry Pi).

### Windows / macOS (Docker Desktop)
Install **Docker Desktop**, create a folder with the `docker-compose.yml` from *Quick start*, then run
`docker compose up -d` in a terminal (PowerShell on Windows, Terminal on macOS) inside that folder.

### Linux desktop / server
Install Docker Engine + the Compose plugin, save the `docker-compose.yml` from *Quick start*, then run
`docker compose up -d`.

---

## Optional features

Turn these on by editing `.env` and running `docker compose up -d` again.

### Protect with a login
Anyone on your network can otherwise reach the app. To require a password:

```ini
AUTH_ENABLED=true
ADMIN_PASSWORD=choose-a-strong-password
```

The username is ignored; only the password matters. The same password also unlocks the OPDS catalog
in e-reader apps. If you expose MangaSama beyond your home network, also put it behind an HTTPS
reverse proxy.

### Automatic backups
```ini
BACKUP_ENABLED=true
```
A daily, safe copy of the database is written to `/config/backups`.

### Sites behind Cloudflare
Some sources occasionally show a Cloudflare challenge. You can run the optional FlareSolverr helper:
uncomment the `flaresolverr` service in `docker-compose.yml` and set `CLOUDFLARE_SOLVER=flaresolverr`
in `.env`. Otherwise MangaSama simply falls back to another source.

---

## Configuration reference

| Env var | Default | Purpose |
|---|---|---|
| `DATA_DIR` | `/data` | Database + downloaded library folders |
| `CONFIG_DIR` | `/config` | Configuration, cookie cache, backups |
| `AUTH_ENABLED` | `false` | Set `true` (with `ADMIN_PASSWORD`) to require a login |
| `ADMIN_PASSWORD` | _(empty)_ | The admin password when auth is on |
| `AUTH_MAX_FAILURES` | `10` | Wrong-password tries before a temporary lockout |
| `AUTH_LOCKOUT_SECONDS` | `60` | How long a client is blocked after too many failures |
| `BACKUP_ENABLED` | `false` | Daily safe DB backup to `/config/backups` |
| `CLOUDFLARE_SOLVER` | unset | `playwright` or `flaresolverr` |
| `CORS_ORIGINS` | localhost dev URLs | Allowed browser origins (dev only; prod is same-origin) |
| `FORWARDED_ALLOW_IPS` | `*` | Proxy IPs trusted for `X-Forwarded-*`; tighten in production |

See [`.env.example`](.env.example) for every option.

### Security

MangaSama is built for a **single user on a trusted home network**, with sensible defaults:

- **Security headers** on every response (CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy`,
  `Permissions-Policy`).
- **Optional login** with a constant-time password check and a **brute-force lockout**.
- **No secret leakage** — the API hides the database path, and unexpected errors return a generic
  message (details are logged on the server only).
- **Dependency hygiene** — Dependabot plus an advisory `pip-audit` / `npm audit` check in CI.

If you ever expose MangaSama to the internet: enable the login, use HTTPS via a reverse proxy, and
restrict `FORWARDED_ALLOW_IPS` to that proxy.

---

## Using MangaSama

1. **Create a library** — give it a name, pick a type (manga / manhua / manhwa), and set a **Root
   path** under `/data` (e.g. `/data/manga_it`).
2. **Search** a series and **Add** it to the library.
3. **Follow** it — MangaSama checks for new chapters on a schedule and downloads them.
4. **Read** — point Komga/Kavita at the same folder, or use the OPDS catalog at
   `http://<host>:8000/opds/v1.2/root` in your e-reader app.

The **Settings** view shows provider/source health and lets you trigger a manual backup.

---

## Documentation

- [docs/architecture.md](docs/architecture.md) — how it works, boot order, data model.
- [docs/api.md](docs/api.md) — REST + OPDS reference (also Swagger at `/api/docs`).
- [docs/sources.md](docs/sources.md) — per-source notes and auto-fallback.
- [docs/comicinfo.md](docs/comicinfo.md) — ComicInfo.xml mapping + CBZ guarantees.
- [CHANGELOG.md](CHANGELOG.md) — release notes & known limitations.

---

## For developers

<details>
<summary>Local dev, tests, project layout, and contributing</summary>

### Run from source

```bash
git clone https://github.com/iCosiSenpai/mangasama.git
cd mangasama
python -m venv .venv && . .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
cd frontend && npm install && npm run build && cd ..
alembic upgrade head
uvicorn app.main:app --reload                  # http://localhost:8000
```

For the frontend dev server with hot reload: `cd frontend && npm run dev` (proxies `/api` + `/opds`
to `:8000`).

### Tests & checks

```bash
pip install -e ".[dev]"
pytest -q                                       # backend test suite
pytest -q --cov=app --cov-report=term-missing   # with coverage
ruff check app tests                            # lint (CI gate)
mypy app                                         # static types (advisory)
cd frontend
npm install
npm run type-check && npm run test && npm run build
node ../tests/frontend/smoke.js                 # backend must be running on :8000
```

CI (`.github/workflows/ci.yml`) runs on every push to `main` and on PRs:

- **Backend**: `ruff` (gate), `mypy` (advisory), `pytest` with coverage.
- **Frontend**: `type-check`, `vitest`, `build`.
- **Security audit** (advisory): `pip-audit` + `npm audit`.

### Architecture

```
Browser ──► FastAPI (Vue 3 SPA served from /)
             ├── /api/*        (REST: libraries, series, chapters, jobs, settings)
             ├── /opds/v1.2/*  (Atom XML for e-readers)
             ├── APScheduler ─── follow_check, domain_health, cleanup, backup
             ├── DownloadQueue ── N asyncio workers ─► CbzPackager
             ├── Scrapers:  MangaDex, MangaWorld
             ├── Metadata:  AniList, MangaDex, GoogleBooks (dormant)
             └── SQLite (libraries, series, volumes, chapters, pages, jobs, ...)
```

### Project layout

```
mangasama/
├── app/                  # Python backend (FastAPI)
│   ├── api/              # routers
│   ├── core/             # http client, rate limiter, auth, paths
│   ├── db/ models/ schemas/
│   ├── scrapers/         # MangaDex + MangaWorld
│   ├── metadata/         # AniList, MangaDex, GoogleBooks
│   ├── services/         # CBZ builder, follow, OPDS, ...
│   ├── scheduler/        # APScheduler jobs
│   └── web/              # built Vue assets (gitignored)
├── frontend/             # Vue 3 + Vite + Tailwind
├── config/               # default.yaml, sources.yaml, logging.yaml
├── migrations/ docker/ tests/
```

Contributions: keep `ruff` clean, add tests, and keep the tree runnable. See
[docs/architecture.md](docs/architecture.md) for the invariants.

</details>

---

## Roadmap

**v0.1.0** ships: MangaDex + MangaWorld scrapers, FlareSolverr Cloudflare bypass, AniList + MangaDex
metadata, follow scheduler, CBZ+ComicInfo, OPDS, Vue 3 UI, single Docker image with auto-seeded
config.

**Planned**: Bato + MangaKakalot + MangaPark scrapers, Playwright CF solver, light novels.

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

MangaSama is for personal archival of legally-obtained content. Respect the rights of scanlators and
publishers. Do not use this tool to redistribute copyrighted material.
