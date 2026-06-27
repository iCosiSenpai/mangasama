"""``/api/admin/settings`` — runtime configuration editable from the GUI."""

from __future__ import annotations

from fastapi import APIRouter

from app.core import setup_state
from app.schemas.admin_settings import AdminSettings, AdminSettingsPatch
from app.settings import get_settings

router = APIRouter(tags=["admin"])


def _settings_to_schema() -> AdminSettings:
    s = get_settings()
    return AdminSettings(
        log_level=s.log_level,  # type: ignore[arg-type]
        backup_enabled=s.backup_enabled,
        backup_retention_days=s.backup_retention_days,
        default_rate_limit_rpm=s.default_rate_limit_rpm,
        scraper_mangapark_enabled=s.scraper_mangapark_enabled,
        scraper_bato_enabled=s.scraper_bato_enabled,
        scraper_mangakakalot_enabled=s.scraper_mangakakalot_enabled,
        scheduler_follow_interval_min=s.scheduler_follow_interval_min,
        scheduler_domain_health_min=s.scheduler_domain_health_min,
        scheduler_job_retention_days=s.scheduler_job_retention_days,
        cloudflare_solver=s.cloudflare_solver,
        flaresolverr_url=s.flaresolverr_url,
        google_books_enabled=s.google_books_enabled,
        mangaeden_enabled=s.mangaeden_enabled,
    )


@router.get("/admin/settings", response_model=AdminSettings)
async def get_admin_settings() -> AdminSettings:
    return _settings_to_schema()


@router.put("/admin/settings", response_model=AdminSettings)
async def update_admin_settings(patch: AdminSettingsPatch) -> AdminSettings:
    """Update runtime settings and persist them to ``/config/settings.yaml``."""
    s = get_settings()
    updates: dict[str, object] = {}
    for key in AdminSettings.model_fields:
        value = getattr(patch, key)
        if value is None:
            continue
        if hasattr(s, key):
            setattr(s, key, value)
            updates[key] = value

    if updates:
        # Merge with existing file to preserve untouched keys.
        current = setup_state.read_runtime_settings()
        current.update(updates)
        setup_state.write_runtime_settings(current)

    return _settings_to_schema()
