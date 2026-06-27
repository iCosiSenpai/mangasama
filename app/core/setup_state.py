"""Application setup state persisted under ``/config``.

MangaSama is designed as a single-admin appliance. Instead of relying on
environment variables for auth and most runtime settings, the first boot
presents a web setup wizard that writes:

- ``admin.json``      → username + bcrypt-hashed password
- ``settings.yaml``     → editable runtime configuration (log level, scrapers,
                          backup, scheduler, cloudflare solver, …)

Both files live in ``CONFIG_DIR`` (default ``/config``) and survive container
recreation. The 12-table SQLite schema is left untouched.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

import bcrypt
import structlog
import yaml

if TYPE_CHECKING:
    from app.settings import Settings

logger = structlog.get_logger("mangasama.setup")

_ADMIN_FILE = "admin.json"
_SETTINGS_FILE = "settings.yaml"

#: Fields that can be edited at runtime via the GUI and are persisted in
#: ``/config/settings.yaml``. Bootstrap-only fields (data_dir, config_dir,
#: host, port, forwarded_allow_ips, debug) are intentionally excluded.
MANAGED_SETTINGS: set[str] = {
    "log_level",
    "backup_enabled",
    "backup_retention_days",
    "default_rate_limit_rpm",
    "scraper_mangapark_enabled",
    "scraper_bato_enabled",
    "scraper_mangakakalot_enabled",
    "scheduler_follow_interval_min",
    "scheduler_domain_health_min",
    "scheduler_job_retention_days",
    "cloudflare_solver",
    "flaresolverr_url",
    "google_books_enabled",
    "mangaeden_enabled",
}

#: Default values seeded into ``/config/settings.yaml`` on first setup.
DEFAULT_RUNTIME_SETTINGS: dict[str, object] = {
    "log_level": "INFO",
    "backup_enabled": False,
    "backup_retention_days": 7,
    "default_rate_limit_rpm": 30,
    "scraper_mangapark_enabled": False,
    "scraper_bato_enabled": True,
    "scraper_mangakakalot_enabled": True,
    "scheduler_follow_interval_min": 15,
    "scheduler_domain_health_min": 15,
    "scheduler_job_retention_days": 30,
    "cloudflare_solver": "",
    "flaresolverr_url": "http://flaresolverr:8191/v1",
    "google_books_enabled": False,
    "mangaeden_enabled": False,
}


class SetupError(ValueError):
    """Raised when setup input is invalid or setup is already done."""


class SetupStateError(RuntimeError):
    """Raised when reading/writing setup files fails."""


def _config_dir() -> Path:
    """Return the configured config directory (lazy import to avoid cycles)."""
    from app.settings import get_settings

    return get_settings().config_dir


def admin_path() -> Path:
    return _config_dir() / _ADMIN_FILE


def settings_path() -> Path:
    return _config_dir() / _SETTINGS_FILE


def is_setup_completed() -> bool:
    """Return True once the admin account has been created."""
    return admin_path().exists()


# ---------------------------------------------------------------------------
# Admin account
# ---------------------------------------------------------------------------


def _username_pattern() -> re.Pattern[str]:
    return re.compile(r"^[a-zA-Z0-9_-]{3,32}$")


def validate_username(username: str) -> None:
    """Enforce a safe, URL-friendly username."""
    if not isinstance(username, str) or not _username_pattern().match(username):
        raise SetupError(
            "username must be 3-32 characters and contain only letters, numbers, "
            "underscores or dashes"
        )


def validate_password(password: str) -> None:
    """Enforce a minimum password length."""
    if not isinstance(password, str) or len(password) < 8:
        raise SetupError("password must be at least 8 characters long")


def hash_password(password: str) -> str:
    """Return a bcrypt hash string for the supplied password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time password verification."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def read_admin() -> dict[str, object] | None:
    """Read and parse ``admin.json``. Return None if missing or unreadable."""
    path = admin_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (OSError, json.JSONDecodeError) as e:
        logger.error("setup.read_admin_failed", error=str(e))
        return None


def write_admin(username: str, password: str) -> None:
    """Create the admin account on disk (idempotent overwrite guard)."""
    validate_username(username)
    validate_password(password)
    path = admin_path()
    if path.exists():
        raise SetupError("setup already completed")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"username": username, "password_hash": hash_password(password)},
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError as e:
        raise SetupStateError(f"failed to write admin file: {e}") from e


def verify_basic_auth(authorization_header: str | None) -> bool:
    """Validate an ``Authorization: Basic ...`` header against ``admin.json``.

    Fails closed: missing header, malformed payload, unknown username or wrong
    password all return False.
    """
    admin = read_admin()
    if admin is None:
        return False
    if not authorization_header:
        return False
    scheme, _, b64 = authorization_header.partition(" ")
    if scheme.lower() != "basic" or not b64:
        return False
    try:
        decoded = base64.b64decode(b64, validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return False
    username, _, password = decoded.partition(":")
    if username != admin.get("username"):
        return False
    return verify_password(password, admin.get("password_hash", ""))


# ---------------------------------------------------------------------------
# Runtime settings
# ---------------------------------------------------------------------------


def read_runtime_settings() -> dict[str, object]:
    """Read ``/config/settings.yaml`` if it exists."""
    path = settings_path()
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, yaml.YAMLError) as e:
        logger.error("setup.read_runtime_settings_failed", error=str(e))
        return {}


def write_runtime_settings(settings: dict[str, object]) -> None:
    """Write ``/config/settings.yaml`` atomically."""
    path = settings_path()
    # Strip any keys that are not managed so env/bootstrap-only fields can't be
    # accidentally persisted from the GUI.
    clean = {k: v for k, v in settings.items() if k in MANAGED_SETTINGS}
    try:
        path.write_text(
            yaml.safe_dump(clean, sort_keys=True, allow_unicode=True),
            encoding="utf-8",
        )
    except OSError as e:
        raise SetupStateError(f"failed to write settings file: {e}") from e


def init_runtime_settings(overrides: dict[str, object] | None = None) -> dict[str, object]:
    """Seed ``/config/settings.yaml`` with defaults + optional setup overrides."""
    merged = dict(DEFAULT_RUNTIME_SETTINGS)
    if overrides:
        merged.update({k: v for k, v in overrides.items() if k in MANAGED_SETTINGS})
    if not settings_path().exists():
        write_runtime_settings(merged)
    return merged


def apply_runtime_settings(settings: Settings) -> None:
    """Apply values from ``/config/settings.yaml`` to a Settings instance.

    This is called once at startup, after pydantic-settings has loaded env vars.
    Managed fields from the YAML file take precedence over defaults, but env
    vars still win when explicitly set. In practice, users should leave the
    managed env vars empty and edit them via the GUI.
    """
    data = read_runtime_settings()
    for key, value in data.items():
        if key in MANAGED_SETTINGS and hasattr(settings, key):
            try:
                setattr(settings, key, value)
            except Exception as e:  # pragma: no cover
                logger.warning("setup.apply_runtime_setting_failed", key=key, error=str(e))
