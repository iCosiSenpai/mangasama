"""Runtime settings editable from the GUI."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AdminSettings(BaseModel):
    """Full runtime settings view exposed to the admin GUI."""

    model_config = ConfigDict(from_attributes=True)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    backup_enabled: bool = False
    backup_retention_days: int = Field(default=7, ge=1, le=365)
    default_rate_limit_rpm: int = Field(default=30, ge=1, le=240)
    scraper_mangapark_enabled: bool = False
    scraper_bato_enabled: bool = True
    scraper_mangakakalot_enabled: bool = True
    scheduler_follow_interval_min: int = Field(default=15, ge=1, le=1440)
    scheduler_domain_health_min: int = Field(default=15, ge=1, le=1440)
    scheduler_job_retention_days: int = Field(default=30, ge=1, le=365)
    cloudflare_solver: Literal["", "playwright", "flaresolverr"] = ""
    flaresolverr_url: str = "http://flaresolverr:8191/v1"
    google_books_enabled: bool = False
    mangaeden_enabled: bool = False


class AdminSettingsPatch(BaseModel):
    """Sparse update for ``PUT /api/admin/settings``."""

    model_config = ConfigDict(extra="forbid")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] | None = None
    backup_enabled: bool | None = None
    backup_retention_days: int | None = Field(default=None, ge=1, le=365)
    default_rate_limit_rpm: int | None = Field(default=None, ge=1, le=240)
    scraper_mangapark_enabled: bool | None = None
    scraper_bato_enabled: bool | None = None
    scraper_mangakakalot_enabled: bool | None = None
    scheduler_follow_interval_min: int | None = Field(default=None, ge=1, le=1440)
    scheduler_domain_health_min: int | None = Field(default=None, ge=1, le=1440)
    scheduler_job_retention_days: int | None = Field(default=None, ge=1, le=365)
    cloudflare_solver: Literal["", "playwright", "flaresolverr"] | None = None
    flaresolverr_url: str | None = None
    google_books_enabled: bool | None = None
    mangaeden_enabled: bool | None = None
