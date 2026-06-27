"""`/api/settings` — effective config + tiny runtime PATCH + provider health."""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import DBSession
from app.schemas.settings_api import (
    EffectiveSettings,
    HealthSnapshot,
    SettingsPatch,
)
from app.services import settings_api as settings_service

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=EffectiveSettings)
async def get_settings() -> EffectiveSettings:
    return settings_service.get_effective_settings()


@router.patch("/settings", response_model=EffectiveSettings)
async def patch_settings(patch: SettingsPatch) -> EffectiveSettings:
    # The Pydantic model is permissive (Optional fields); the service
    # enforces the allow-list and raises ValueError → 400 for unknowns.
    return settings_service.patch_settings(patch.model_dump(exclude_none=True))


@router.get("/settings/providers/health", response_model=HealthSnapshot)
async def providers_health(session: DBSession) -> HealthSnapshot:
    return await settings_service.get_provider_health(session)


@router.post("/settings/providers/health/check", response_model=HealthSnapshot)
async def run_providers_health_check(session: DBSession) -> HealthSnapshot:
    """Ping all source domains now and return the refreshed snapshot."""
    from app.services.health import check_all_domains

    await check_all_domains()
    return await settings_service.get_provider_health(session)


@router.post("/settings/providers/{source}/reset", response_model=HealthSnapshot)
async def reset_provider(source: str, session: DBSession) -> HealthSnapshot:
    """Admin: clear a source's failure state (re-enable a flipped domain)."""
    from app.scrapers.registry import get_scraper_registry

    if source not in get_scraper_registry().names():
        raise ValueError(f"unknown provider: {source!r}")
    await settings_service.reset_provider_health(session, source)
    await session.commit()
    return await settings_service.get_provider_health(session)


@router.post("/settings/backup")
async def run_backup() -> dict:
    """Admin: create a WAL-safe SQLite backup now (works regardless of BACKUP_ENABLED)."""
    import asyncio

    from app.services.backup import create_backup, list_backups

    path = await asyncio.to_thread(create_backup)
    return {
        "created": path.name,
        "size_bytes": path.stat().st_size,
        "total_backups": len(list_backups()),
    }
