"""Chapter schemas — request/response DTOs for the `chapters` + `pages` tables."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChapterRead(BaseModel):
    """Full chapter detail."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    volume_id: int
    number: str
    sort: float
    title: str | None = None
    source_provider: str
    source_id: str
    language: str
    pages_count: int | None = None
    file_path: str | None = None
    cbz_size: int | None = None
    cbz_sha256: str | None = None
    downloaded_at: datetime | None = None
    source_url: str | None = None
    comic_info_id: str | None = None
    created_at: datetime


class ChapterListItem(BaseModel):
    """Lighter payload for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    volume_id: int
    number: str
    title: str | None = None
    language: str
    pages_count: int | None = None
    downloaded_at: datetime | None = None
    cbz_size: int | None = None
    source_provider: str
