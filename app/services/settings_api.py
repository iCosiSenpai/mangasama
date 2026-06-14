"""Settings service — effective config + small runtime overrides.

The PATCH endpoint only allows flipping a small, safe subset of
settings at runtime. Anything else returns 400.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import DomainHealth
from app.schemas.settings_api import (
    EffectiveSettings,
    HealthSnapshot,
    ProviderHealth,
)
from app.scrapers.registry import get_scraper_registry
from app.settings import Settings, get_settings
from app import __version__

logger = structlog.get_logger("mangasama.services.settings")


def get_effective_settings() -> EffectiveSettings:
    s: Settings = get_settings()
    registry = get_scraper_registry()
    known = registry.names()
    # A scraper is "enabled" if it shows up in `library_defaults()`'s
    # default provider list — that's the only signal we expose today.
    defaults = s.library_defaults()
    enabled = [name for name in known if name in defaults.get("default_providers", [])]
    return EffectiveSettings(
        app_name=s.app_name,
        version=__version__,
        log_level=s.log_level,
        data_dir=str(s.data_dir),
        config_dir=str(s.config_dir),
        db_url=s.db_url,
        library_defaults=defaults,
        known_scrapers=known,
        enabled_scrapers=enabled,
    )


def patch_settings(patch_dict: dict) -> EffectiveSettings:
    """Apply a small subset of runtime overrides and return the new view.

    Unknown keys raise `ValueError` (HTTP 400 at the boundary).
    """
    s = get_settings()
    allowed = {"log_level", "default_rate_limit_rpm"}
    bad = set(patch_dict) - allowed
    if bad:
        raise ValueError(f"unknown settings keys: {sorted(bad)!r}")
    for k, v in patch_dict.items():
        if v is None:
            continue
        if hasattr(s, k):
            setattr(s, k, v)
    return get_effective_settings()


async def get_provider_health(session: AsyncSession) -> HealthSnapshot:
    """Snapshot of `domain_health` rows, joined with the known scrapers.

    A scraper with no rows in `domain_health` is reported as healthy by
    default (we've never pinged it).
    """
    rows = (await session.execute(select(DomainHealth))).scalars().all()
    by_source: dict[str, ProviderHealth] = {}
    for r in rows:
        by_source[r.source] = ProviderHealth(
            provider=r.source,
            healthy=r.healthy,
            last_ok=r.last_ok,
            last_fail=r.last_fail,
            fail_count=r.fail_count,
            last_status_code=r.last_status_code,
        )
    # Add any known scrapers we haven't recorded yet.
    registry = get_scraper_registry()
    for name in registry.names():
        by_source.setdefault(name, ProviderHealth(provider=name, healthy=True))
    return HealthSnapshot(providers=list(by_source.values()))


async def reset_provider_health(session: AsyncSession, source: str) -> int:
    """Clear the failure state of every domain of `source`.

    Sets `healthy=True` and `fail_count=0`. Returns the number of rows
    reset (0 if the source has no recorded domains).
    """
    rows = (
        await session.execute(select(DomainHealth).where(DomainHealth.source == source))
    ).scalars().all()
    for r in rows:
        r.healthy = True
        r.fail_count = 0
    return len(rows)


__all__ = [
    "get_effective_settings",
    "get_provider_health",
    "patch_settings",
    "reset_provider_health",
]
