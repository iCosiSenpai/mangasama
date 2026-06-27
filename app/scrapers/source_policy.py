"""Source enablement policy — YAML flags + env toggles.

A source may be listed in `config/sources.yaml` but still unavailable if:
  - `enabled: false` in YAML
  - an env toggle disables it (e.g. `SCRAPER_MANGAPARK_ENABLED=false`)
  - no scraper is registered for it
"""

from __future__ import annotations

from app.scrapers.domain_registry import DomainRegistry
from app.scrapers.registry import get_scraper_registry
from app.settings import get_settings

# Env-gated optional sources (no scraper or opt-in tier-2).
_ENV_GATED: dict[str, str] = {
    "mangaeden": "mangaeden_enabled",
    "mangapark": "scraper_mangapark_enabled",
    "bato": "scraper_bato_enabled",
    "mangakakalot": "scraper_mangakakalot_enabled",
}


def is_source_enabled(source: str, *, registry: DomainRegistry | None = None) -> bool:
    """Return True when a source is enabled in YAML and not blocked by env."""
    reg = registry or DomainRegistry()
    cfg = reg.get(source)
    if not cfg or not cfg.get("enabled", False):
        return False
    settings = get_settings()
    env_field = _ENV_GATED.get(source)
    if env_field:
        return bool(getattr(settings, env_field, False))
    return True


def is_scraper_available(name: str, *, registry: DomainRegistry | None = None) -> bool:
    """Registered scraper whose source is enabled."""
    if not get_scraper_registry().has(name):
        return False
    return is_source_enabled(name, registry=registry)


def enabled_scraper_names(*, registry: DomainRegistry | None = None) -> list[str]:
    """All registered scrapers that are currently available."""
    return [
        name for name in get_scraper_registry().names()
        if is_scraper_available(name, registry=registry)
    ]


__all__ = ["enabled_scraper_names", "is_scraper_available", "is_source_enabled"]
