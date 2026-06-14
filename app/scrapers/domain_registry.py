"""Domain registry: load `config/sources.yaml`, track per-domain health.

The DomainRegistry is the *only* thing that knows "which domain of
which source is healthy right now". Concrete scrapers call
`pick_domain(source)` to resolve `mangaworld` → `mangaworld.mx` (or one
of the alternates, depending on health).

The health tracking itself is persisted in the `domain_health` DB table
(seeded by `migrations/versions/0002_seed_sources.py` and re-seeded at
every startup by `app/db/init.py`). The cron in
`app/services/health.py` (step 15) updates the `healthy` flag; this
class reads it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

from app.settings import get_settings

logger = structlog.get_logger("mangasama.scrapers.domain_registry")


class DomainRegistry:
    """YAML-driven, DB-backed domain selection per source."""

    def __init__(self, sources_path: Path | None = None):
        self._sources_path = sources_path or get_settings().config_dir / "sources.yaml"
        self._cache: dict[str, dict[str, Any]] = {}

    # -------------------------------------------------------------- loading

    def _load(self) -> None:
        """(Re)load the YAML. Idempotent — call after a config edit."""
        if not self._sources_path.exists():
            logger.warning(
                "domain_registry.yaml_missing", path=str(self._sources_path),
            )
            self._cache = {}
            return
        with self._sources_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        sources: dict[str, Any] = data.get("sources") or {}
        self._cache = sources
        logger.info("domain_registry.loaded", count=len(sources))

    def sources(self) -> dict[str, dict[str, Any]]:
        """Return a copy of the parsed YAML, lazy-loaded on first call."""
        if not self._cache:
            self._load()
        return self._cache

    def get(self, source: str) -> dict[str, Any] | None:
        return self.sources().get(source)

    def all_source_names(self) -> list[str]:
        return list(self.sources().keys())

    def all_domains_for(self, source: str) -> list[str]:
        cfg = self.get(source) or {}
        primary = cfg.get("primary")
        alts = cfg.get("alternates") or []
        return [d for d in [primary, *alts] if d]

    # -------------------------------------------------------- domain pick

    async def pick_domain(self, source: str) -> str | None:
        """Pick the healthiest domain for `source`.

        Resolution order:
          1. `primary`, if healthy in DB or no row yet
          2. alternates, sorted by lowest `fail_count` among healthy rows
          3. the lowest `fail_count` row, even if unhealthy (last resort)

        If the source isn't in the YAML, return None.
        """
        cfg = self.get(source)
        if not cfg:
            return None
        primary = cfg.get("primary")
        if not primary:
            return None

        # Lazy import to avoid loading the DB at module import.
        from sqlalchemy import select

        from app.db.session import session_scope
        from app.models import DomainHealth

        async with session_scope() as session:
            stmt = select(DomainHealth).where(DomainHealth.source == source)
            rows = (await session.execute(stmt)).scalars().all()
        by_domain: dict[str, DomainHealth] = {r.domain: r for r in rows}

        # If the primary has no row yet, prefer it (no evidence of failure).
        if primary not in by_domain:
            return primary
        if by_domain[primary].healthy and by_domain[primary].fail_count == 0:
            return primary

        # Otherwise sort candidates (primary + alternates) by health, then fails.
        candidates: list[DomainHealth] = []
        for d in self.all_domains_for(source):
            row = by_domain.get(d)
            if row is not None:
                candidates.append(row)
        if not candidates:
            return primary

        candidates.sort(
            key=lambda r: (not r.healthy, r.fail_count, r.last_fail or datetime.min.replace(tzinfo=UTC))
        )
        return candidates[0].domain

    # ---------------------------------------------------------- recording

    async def record_success(self, source: str, domain: str, *, status_code: int | None = None) -> None:
        """Mark (source, domain) as healthy, resetting fail_count."""
        await self._update(source, domain, success=True, status_code=status_code)

    async def record_failure(self, source: str, domain: str, *, status_code: int | None = None) -> None:
        """Increment fail_count; if >= 3, flip healthy=False (the cron may flip back later)."""
        await self._update(source, domain, success=False, status_code=status_code)

    async def _update(
        self,
        source: str,
        domain: str,
        *,
        success: bool,
        status_code: int | None = None,
    ) -> None:
        from datetime import datetime

        from sqlalchemy import select

        from app.db.session import session_scope
        from app.models import DomainHealth

        now = datetime.now(UTC)
        async with session_scope() as session:
            # Read current state.
            stmt = select(DomainHealth).where(
                DomainHealth.source == source, DomainHealth.domain == domain,
            )
            row = (await session.execute(stmt)).scalars().first()
            if row is None:
                # Insert a fresh row. A first-ever failure must count as 1
                # (otherwise the very first failure is silently dropped and
                # it takes 4 failures to flip instead of 3).
                fail_count = 0 if success else 1
                row = DomainHealth(
                    source=source,
                    domain=domain,
                    healthy=success or fail_count < 3,
                    fail_count=fail_count,
                    last_ok=now if success else None,
                    last_fail=None if success else now,
                    last_status_code=status_code,
                )
                session.add(row)
                await session.commit()
                return
            if success:
                row.healthy = True
                row.fail_count = 0
                row.last_ok = now
                row.last_status_code = status_code
            else:
                row.fail_count = (row.fail_count or 0) + 1
                row.last_fail = now
                row.last_status_code = status_code
                if row.fail_count >= 3:
                    row.healthy = False
            await session.commit()
