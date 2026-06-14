"""Settings API schemas — runtime config + provider health."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EffectiveSettings(BaseModel):
    """Response for `GET /api/settings`."""

    model_config = ConfigDict(from_attributes=True)

    app_name: str
    version: str
    log_level: str
    data_dir: str
    config_dir: str
    db_url: str
    library_defaults: dict
    known_scrapers: list[str]
    enabled_scrapers: list[str]


class SettingsPatch(BaseModel):
    """Body for `PATCH /api/settings`.

    Only a small subset of settings is safe to flip at runtime; anything
    outside this subset is rejected with 400.
    """

    model_config = ConfigDict(extra="forbid")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] | None = None
    default_rate_limit_rpm: int | None = Field(default=None, ge=1, le=240)


class ProviderHealth(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    healthy: bool
    last_ok: datetime | None = None
    last_fail: datetime | None = None
    fail_count: int = 0
    last_status_code: int | None = None


class HealthSnapshot(BaseModel):
    providers: list[ProviderHealth] = Field(default_factory=list)
