"""Application settings, loaded from env vars with YAML defaults."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Resolution order (later wins):
        1. `config/default.yaml`
        2. Environment variables
        3. `.env` file (loaded via pydantic-settings)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core
    app_name: str = "MangaSama"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    debug: bool = False

    # Paths
    data_dir: Path = Field(default=Path("/data"))
    config_dir: Path = Field(default=Path("/config"))
    db_filename: str = "mangasama.db"
    downloads_dir: str = "downloads"

    # HTTP server
    host: str = "0.0.0.0"
    port: int = 8000

    # Auth
    auth_enabled: bool = False
    admin_password: str = ""
    # Brute-force mitigation for the Basic gate: after `auth_max_failures`
    # wrong-password attempts from one client within the window, that client
    # is locked out (HTTP 429) for `auth_lockout_seconds`.
    auth_max_failures: int = 10
    auth_lockout_seconds: int = 60

    # CORS: comma-separated list of allowed origins for the dev frontend.
    # Production serves the SPA same-origin, so this is dev-only by default.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Which client IPs uvicorn trusts for X-Forwarded-* headers. Default "*"
    # assumes a single isolated reverse proxy; tighten to proxy CIDRs in prod.
    forwarded_allow_ips: str = "*"

    # Cloudflare
    cloudflare_solver: Literal["", "playwright", "flaresolverr"] = ""
    flaresolverr_url: str = "http://flaresolverr:8191/v1"

    # Scrapers
    default_rate_limit_rpm: int = 30
    scraper_concurrency: int = 4
    user_agent: str = "MangaSama/0.1 (+https://github.com/mangasama/mangasama)"
    # Whether the shared httpx client opens HTTP/2. Off by default
    # because the respx-based test suite can't intercept HTTP/2 calls
    # (httpx's HTTP/2 transport path is incompatible with respx's
    # mocking). Flip on in production if you want HTTP/2.
    http2_enabled: bool = False

    # AniList
    anilist_url: str = "https://graphql.anilist.co"
    anilist_rate_limit_rpm: int = 30

    # MangaDex
    mangadex_url: str = "https://api.mangadex.org"
    mangadex_rate_limit_rpm: int = 40

    # MangaWorld
    mangaworld_url: str = "https://www.mangaworld.mx"
    mangaworld_rate_limit_rpm: int = 20

    # MangaEden — defunct as of 2026-06 (domain redirected). Kept here
    # for forward-compat in case a mirror reappears.
    mangaeden_url: str = "https://www.mangaeden.com"
    mangaeden_enabled: bool = False
    mangaeden_rate_limit_rpm: int = 30

    # Google Books
    google_books_url: str = "https://www.googleapis.com/books/v1"
    google_books_api_key: str = ""
    google_books_enabled: bool = False

    # Optional scrapers
    scraper_mangapark_enabled: bool = False
    scraper_bato_enabled: bool = True
    scraper_mangakakalot_enabled: bool = True

    # Scheduler
    scheduler_follow_interval_min: int = 15
    scheduler_domain_health_min: int = 15
    scheduler_job_retention_days: int = 30

    # Download
    download_worker_count: int = 3
    download_queue_size: int = 200

    # Backup
    backup_enabled: bool = False
    backup_retention_days: int = 7

    # Frontend
    frontend_out_dir: str = "app/web"

    # --------------------------------------------------------------- computed

    @property
    def db_url(self) -> str:
        """SQLAlchemy URL for the SQLite file."""
        db_path = self.data_dir / self.db_filename
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{db_path.as_posix()}"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parsed CORS origins (comma-separated env → list)."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def db_sync_url(self) -> str:
        """Sync URL — used by Alembic which doesn't need async."""
        db_path = self.data_dir / self.db_filename
        return f"sqlite:///{db_path.as_posix()}"

    @property
    def cookies_dir(self) -> Path:
        p = self.config_dir / "cookies"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cache_dir(self) -> Path:
        p = self.config_dir / ".cache"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def backups_dir(self) -> Path:
        p = self.config_dir / "backups"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def downloads_path(self) -> Path:
        p = self.data_dir / self.downloads_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def covers_path(self) -> Path:
        p = self.data_dir / "covers"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def load_yaml_defaults(self) -> None:
        """Merge config/default.yaml and config/sources.yaml into self.

        Environment variables and explicit pydantic fields take precedence.
        This is called once at app startup; afterwards the YAML values act
        as defaults that env can override.
        """
        default_path = self.config_dir / "default.yaml"
        if not default_path.exists():
            return
        with default_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        library = data.get("library", {})
        if "default_providers" in library:
            self._yaml_default_providers: list[str] = library["default_providers"]
        if "default_folder_strategy" in library:
            self._yaml_folder_strategy: str = library["default_folder_strategy"]
        if "default_italian_priority" in library:
            self._yaml_italian_priority: bool = library["default_italian_priority"]
        if "default_follow_interval_hours" in library:
            self._yaml_follow_interval_hours: int = library["default_follow_interval_hours"]
        if "default_jpg_quality" in library:
            self._yaml_jpg_quality: int = library["default_jpg_quality"]

    # Library defaults (populated by load_yaml_defaults)
    _yaml_default_providers: list[str] = ["mangaworld", "mangadex"]
    _yaml_folder_strategy: str = "series_volume_chapter"
    _yaml_italian_priority: bool = True
    _yaml_follow_interval_hours: int = 24
    _yaml_jpg_quality: int = 85

    def library_defaults(self) -> dict:
        return {
            "default_providers": self._yaml_default_providers,
            "default_folder_strategy": self._yaml_folder_strategy,
            "default_italian_priority": self._yaml_italian_priority,
            "default_follow_interval_hours": self._yaml_follow_interval_hours,
            "default_jpg_quality": self._yaml_jpg_quality,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor."""
    s = Settings()
    s.load_yaml_defaults()
    return s
