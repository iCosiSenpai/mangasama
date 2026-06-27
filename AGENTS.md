# AGENTS.md

This repo is **MangaSama**, a single-process FastAPI (Python 3.12) backend + Vue 3/Vite
frontend. For project architecture, invariants, and the full command list see `CLAUDE.md`
and `README.md` (they are authoritative — don't duplicate them here).

## Cursor Cloud specific instructions

The update script already runs `pip install -e ".[dev]"` and `npm --prefix frontend install`
on startup, so dependencies are present. Notes below cover non-obvious caveats for this VM.

- **Use `python3`, not `python`** — there is no `python` alias on this VM. Run modules as
  `python3 -m uvicorn ...`, `python3 -m alembic ...`, `python3 -m pytest`, etc.
- **Console scripts aren't on `PATH`** — pip installs `uvicorn`/`alembic`/`pytest`/`ruff` into
  `~/.local/bin`, which isn't on `PATH` by default. Either prepend it
  (`export PATH="$HOME/.local/bin:$PATH"`) or just use `python3 -m <tool>`.
- **Don't use the default `/data` and `/config`** — they aren't writable here. For local dev,
  point at repo-local dirs and seed the YAML config (mirrors what `docker/entrypoint.sh` does):
  ```bash
  mkdir -p dev_data dev_config
  cp config/default.yaml config/sources.yaml config/logging.yaml dev_config/
  ```
  Then prefix run/migrate commands with `DATA_DIR=./dev_data CONFIG_DIR=./dev_config`.
- **Run migrations before first start**: `DATA_DIR=./dev_data CONFIG_DIR=./dev_config python3 -m alembic upgrade head`.
- **Build the frontend before running the backend** if you want the UI at `:8000` — the SPA is
  served from `app/web/`, which is gitignored and produced by `cd frontend && npm run build`.
  The build/migrations are intentionally NOT in the update script (it only refreshes deps), so
  do them yourself in the setup session.
- **Run the dev server** (serves SPA + REST + OPDS + scheduler in one process):
  ```bash
  DATA_DIR=./dev_data CONFIG_DIR=./dev_config python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```
  Health check: `curl http://localhost:8000/api/health`. The Vite dev server
  (`cd frontend && npm run dev`, port 5173) is only needed for frontend hot-reload and proxies
  `/api` + `/opds` to `:8000`.
- **Backend tests are mock-based** (`respx`) — `python3 -m pytest -q` needs no network or running
  server, but the full suite takes ~100s. Lint gate: `ruff check app tests`.
