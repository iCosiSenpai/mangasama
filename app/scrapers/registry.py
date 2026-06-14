"""Scraper registry: name -> BaseScraper instance.

The registry is the only place that knows which scrapers exist and how
to instantiate them. The orchestrator and the API call
`get_scraper("mangadex")` to get a ready-to-use instance.

Scrapers that are disabled in `sources.yaml` (or via env) are still
registered but their `enabled` is False; callers can check before using
them.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

import structlog

from app.scrapers.base import BaseScraper

logger = structlog.get_logger("mangasama.scrapers.registry")


class ScraperRegistry:
    """Lazy, name-indexed collection of scraper instances."""

    def __init__(self) -> None:
        self._instances: dict[str, BaseScraper] = {}
        self._loaded = False

    # --------------------------------------------------------------- build

    def load_all(self) -> None:
        """Import every module in `app/scrapers/` and instantiate their scrapers.

        A module is expected to expose a class that subclasses BaseScraper.
        We auto-discover via `pkgutil.iter_modules` so adding a new scraper
        file (e.g. `mangakakalot.py`) is enough — no edits here.
        """
        import app.scrapers as pkg

        for mod_info in pkgutil.iter_modules(pkg.__path__):
            if mod_info.name in {"base", "registry", "domain_registry", "cookies", "cloudflare"}:
                continue
            mod = importlib.import_module(f"app.scrapers.{mod_info.name}")
            for attr_name in dir(mod):
                cls = getattr(mod, attr_name)
                if (
                    isinstance(cls, type)
                    and issubclass(cls, BaseScraper)
                    and cls is not BaseScraper
                    and getattr(cls, "name", "")
                ):
                    self.register(cls())
        self._loaded = True
        logger.info("scraper_registry.loaded", count=len(self._instances))

    def register(self, scraper: BaseScraper) -> None:
        if not scraper.name:
            raise ValueError(f"Scraper {scraper!r} has no `name`")
        if scraper.name in self._instances:
            logger.warning("scraper_registry.duplicate", name=scraper.name)
            return
        self._instances[scraper.name] = scraper

    # -------------------------------------------------------------- access

    def get(self, name: str) -> BaseScraper:
        if not self._loaded:
            self.load_all()
        if name not in self._instances:
            raise KeyError(f"No scraper registered as {name!r}")
        return self._instances[name]

    def has(self, name: str) -> bool:
        if not self._loaded:
            self.load_all()
        return name in self._instances

    def all(self) -> dict[str, BaseScraper]:
        if not self._loaded:
            self.load_all()
        return dict(self._instances)

    def names(self) -> list[str]:
        if not self._loaded:
            self.load_all()
        return list(self._instances.keys())


# Module-level singleton, populated by `load_all()` on first access.
_registry: ScraperRegistry | None = None


def get_scraper_registry() -> ScraperRegistry:
    global _registry
    if _registry is None:
        _registry = ScraperRegistry()
        _registry.load_all()
    return _registry


def get_scraper(name: str) -> BaseScraper:
    return get_scraper_registry().get(name)


def reset_for_tests() -> None:
    """Drop the registry (test helper)."""
    global _registry
    _registry = None
