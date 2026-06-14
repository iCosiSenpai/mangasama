"""FastAPI application entry point.

This is the runtime core of MangaSama. It wires:
  - Settings + structured logging
  - DB session lifecycle
  - Static frontend (built Vue assets) at /
  - REST API at /api/*
  - OPDS at /opds/v1.2/*
  - APScheduler jobs (follow check, domain health, cleanup)
  - Download queue workers (in-process)

Lifespan order:
  1. settings (env + YAML)
  2. logging
  3. db init (create_all for first run; Alembic otherwise)
  4. scraper registry
  5. download queue + workers
  6. scheduler
  7. shutdown: drain queue, flush jobs
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.logging_config import configure_logging, get_logger
from app.settings import get_settings

logger = get_logger("mangasama.main")

# Track app start time for /api/health uptime.
_started_at: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: init/teardown."""
    global _started_at
    settings = get_settings()
    _started_at = time.time()

    configure_logging(level=settings.log_level, config_path=settings.config_dir / "logging.yaml")
    logger.info(
        "mangasama.startup",
        version=__version__,
        data_dir=str(settings.data_dir),
        config_dir=str(settings.config_dir),
    )

    # Ensure runtime dirs.
    for p in (
        settings.data_dir,
        settings.cookies_dir,
        settings.cache_dir,
        settings.backups_dir,
        settings.downloads_path,
        settings.covers_path,
    ):
        Path(p).mkdir(parents=True, exist_ok=True)

    # Database init (create_all is a safety net for first-run; Alembic is the
    # source of truth in production).
    try:
        from app.db.init import init_db
        await init_db()
    except Exception as e:
        logger.error("mangasama.db_init_failed", error=str(e))
        # Don't kill startup — surface the error in /api/health.

    # Shared HTTP client for all scrapers + metadata providers.
    try:
        from app.core.http_client import start_http, stop_http
        await start_http()
        app.state.stop_http = stop_http
    except Exception as e:
        logger.error("mangasama.http_client_init_failed", error=str(e))

    # Download queue + workers.
    # (Defer to step 11 implementation; currently a no-op stub.)
    try:
        from app.services.downloader import start_download_workers, stop_download_workers
        await start_download_workers()
        app.state.stop_download_workers = stop_download_workers
    except ImportError:
        logger.warning("mangasama.download_queue_not_yet_implemented")
    except Exception as e:
        logger.error("mangasama.download_queue_init_failed", error=str(e))

    # APScheduler.
    try:
        from app.scheduler.jobs import start_scheduler, stop_scheduler
        start_scheduler()
        app.state.stop_scheduler = stop_scheduler
    except ImportError:
        logger.warning("mangasama.scheduler_not_yet_implemented")
    except Exception as e:
        logger.error("mangasama.scheduler_init_failed", error=str(e))

    logger.info("mangasama.ready", port=settings.port)

    try:
        yield
    finally:
        logger.info("mangasama.shutdown")
        if hasattr(app.state, "stop_http"):
            try:
                await app.state.stop_http()
            except Exception as e:
                logger.error("mangasama.http_client_stop_failed", error=str(e))
        if hasattr(app.state, "stop_scheduler"):
            try:
                app.state.stop_scheduler()
            except Exception as e:
                logger.error("mangasama.scheduler_stop_failed", error=str(e))
        if hasattr(app.state, "stop_download_workers"):
            try:
                await app.state.stop_download_workers()
            except Exception as e:
                logger.error("mangasama.download_workers_stop_failed", error=str(e))


def _path_needs_auth(path: str) -> bool:
    """Protect the API and OPDS catalog; leave `/api/health` and the SPA
    static assets public."""
    if path == "/api/health":
        return False
    return path.startswith("/api") or path.startswith("/opds")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="MangaSama",
        version=__version__,
        description="Personal archival manga downloader — Italian-first sources.",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # CORS for local dev (Vite runs on a different port).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Optional single-admin HTTP Basic gate over /api and /opds. No-op unless
    # AUTH_ENABLED=true. `/api/health` and the SPA static stay public so the
    # Docker healthcheck and the login page can load.
    @app.middleware("http")
    async def _auth_guard(request, call_next):
        settings = get_settings()
        if (
            settings.auth_enabled
            and request.method != "OPTIONS"
            and _path_needs_auth(request.url.path)
        ):
            from app.core.auth import check_basic_auth

            if not check_basic_auth(request.headers.get("Authorization"), settings.admin_password):
                return Response(
                    status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="MangaSama"'},
                )
        return await call_next(request)

    # Static frontend (built Vue app).
    web_dir = Path(settings.frontend_out_dir)
    if not web_dir.is_absolute():
        web_dir = Path(__file__).resolve().parent.parent / web_dir
    if web_dir.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=web_dir / "assets", check_dir=False),
            name="assets",
        )

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        async def spa_index() -> Response:
            return HTMLResponse((web_dir / "index.html").read_text(encoding="utf-8"))

        @app.get("/favicon.ico", include_in_schema=False)
        async def favicon() -> Response:
            fav = web_dir / "favicon.ico"
            if fav.exists():
                return Response(content=fav.read_bytes(), media_type="image/x-icon")
            return Response(status_code=204)
    else:
        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        async def placeholder_index() -> HTMLResponse:
            return HTMLResponse(
                f"<!doctype html><html><body style='font-family:system-ui;padding:2em'>"
                f"<h1>MangaSama</h1><p>Version {__version__}</p>"
                f"<p>Frontend not yet built. Run <code>cd frontend && npm run build</code> "
                f"or see <a href='/api/docs'>/api/docs</a>.</p></body></html>"
            )

    # Health endpoint — always available, no router required.
    @app.get("/api/health", tags=["health"])
    async def health() -> JSONResponse:
        uptime = time.time() - _started_at if _started_at else 0.0
        return JSONResponse(
            {
                "status": "ok",
                "app": settings.app_name,
                "version": __version__,
                "uptime_seconds": round(uptime, 2),
                "data_dir": str(settings.data_dir),
                "config_dir": str(settings.config_dir),
            }
        )

    # Domain exception → JSON mapping.
    from app.api.exception_handlers import install_exception_handlers
    install_exception_handlers(app)

    # Routers — registered defensively (later steps add them).
    _try_include_routers(app)

    return app


def _try_include_routers(app: FastAPI) -> None:
    """Mount all API routers if their modules are present.

    Each step of the build adds new routers; missing ones are skipped so
    the partial implementation always boots.
    """
    for module_path, prefix in (
        ("app.api.libraries", "/api"),
        ("app.api.series", "/api"),
        ("app.api.chapters", "/api"),
        ("app.api.search", "/api"),
        ("app.api.follow", "/api"),
        ("app.api.jobs", "/api"),
        ("app.api.covers", "/api"),
        ("app.api.settings_api", "/api"),
        ("app.api.opds", ""),
    ):
        try:
            mod = __import__(module_path, fromlist=["router"])
            if hasattr(mod, "router"):
                app.include_router(mod.router, prefix=prefix)
        except ImportError:
            pass  # not yet implemented
        except Exception as e:  # pragma: no cover
            logger.error("mangasama.router_mount_failed", module=module_path, error=str(e))


app = create_app()


def main() -> None:  # pragma: no cover
    """Console entry point: `python -m app`."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":  # pragma: no cover
    main()
