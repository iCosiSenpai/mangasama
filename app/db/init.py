"""Database initialization.

Alembic is the source of truth for schema migrations. This module is a
safety net for fresh installs where Alembic hasn't run yet, and also
re-seeds runtime data (e.g. `domain_health` from `config/sources.yaml`)
on every startup so the YAML stays the source of truth.
"""

from __future__ import annotations

import structlog
import yaml
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base, get_engine, get_sessionmaker
from app.models import DomainHealth
from app.settings import get_settings

logger = structlog.get_logger("mangasama.db.init")


async def init_db() -> None:
    """Create all tables that don't yet exist, and re-seed runtime data.

    Safe to call on every startup. In production, prefer running
    `alembic upgrade head` (the entrypoint.sh does this).
    """
    settings = get_settings()
    engine: AsyncEngine = get_engine(settings)
    async with engine.begin() as conn:
        # Import all models so they're registered on Base.metadata.
        from app.models import orm  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
    logger.info("mangasama.db.init_ok", url=settings.db_url)

    # Re-seed runtime data from YAML (idempotent: INSERT OR IGNORE).
    await _reseed_domain_health()


async def _reseed_domain_health() -> None:
    """Ensure every (source, domain) pair in sources.yaml is in domain_health.

    New sources added to the YAML are picked up at next startup. Existing
    rows (e.g. with `fail_count > 0` from the health cron) are not touched.
    """
    settings = get_settings()
    sources_path = settings.config_dir / "sources.yaml"
    if not sources_path.exists():
        return

    with sources_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    sources: dict = data.get("sources") or {}

    rows: list[dict] = []
    for name, cfg in sources.items():
        if not cfg.get("enabled", True):
            continue
        if cfg.get("primary"):
            rows.append({
                "source": name,
                "domain": cfg["primary"],
                "healthy": True,
                "fail_count": 0,
            })
        for alt in cfg.get("alternates") or []:
            rows.append({
                "source": name,
                "domain": alt,
                "healthy": True,
                "fail_count": 0,
            })

    if not rows:
        return

    sm = get_sessionmaker(settings)
    async with sm() as session:
        # INSERT OR IGNORE — only inserts if (source, domain) doesn't exist.
        # Uses the composite PK, so existing rows with fail_count > 0 stay intact.
        stmt = sqlite_insert(DomainHealth).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["source", "domain"])
        await session.execute(stmt)
        await session.commit()

    logger.info("mangasama.db.domain_health_seeded", rows=len(rows))
