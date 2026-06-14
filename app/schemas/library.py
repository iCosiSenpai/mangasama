"""Library schemas — request/response DTOs for the `libraries` table."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.folder_strategy import LIBRARY_FOLDER_STRATEGIES

#: Allowed content types — anything else (novel, comic, webtoon) is rejected.
LibraryType = Literal["manga", "manhua", "manhwa"]
#: Allowed folder strategies — values come from `app.services.folder_strategy`.
LibraryFolderStrategy = Literal["series_volume_chapter", "series_volume", "chapter_flat", "onefile_per_volume"]


class LibraryBase(BaseModel):
    """Fields shared by create + read. Used as the response type for read."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=120)
    type: LibraryType
    root_path: str = Field(..., min_length=1, max_length=1024)
    folder_strategy: LibraryFolderStrategy = "series_volume_chapter"
    cover_strategy: str = Field(default="series_first", max_length=32)
    providers: list[str] = Field(default_factory=list)
    italian_priority: bool = True
    follow_interval_hours: int = Field(default=24, ge=1, le=8760)
    jpg_quality: int = Field(default=85, ge=1, le=100)

    @field_validator("folder_strategy")
    @classmethod
    def _check_strategy(cls, v: str) -> str:
        if v not in LIBRARY_FOLDER_STRATEGIES:
            raise ValueError(
                f"folder_strategy must be one of {LIBRARY_FOLDER_STRATEGIES}, got {v!r}"
            )
        return v


class LibraryCreate(LibraryBase):
    """Body for `POST /api/libraries`."""


class LibraryUpdate(BaseModel):
    """Body for `PATCH /api/libraries/{id}`. None = don't touch."""

    model_config = ConfigDict(from_attributes=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: LibraryType | None = None
    root_path: str | None = Field(default=None, min_length=1, max_length=1024)
    folder_strategy: LibraryFolderStrategy | None = None
    cover_strategy: str | None = Field(default=None, max_length=32)
    providers: list[str] | None = None
    italian_priority: bool | None = None
    follow_interval_hours: int | None = Field(default=None, ge=1, le=8760)
    jpg_quality: int | None = Field(default=None, ge=1, le=100)


class LibraryRead(LibraryBase):
    """Response for GET endpoints. Adds the row id + timestamps + counts."""

    id: int
    series_count: int = 0
    created_at: datetime
    updated_at: datetime
    deleted: bool = False


class LibraryStats(BaseModel):
    """GET /api/libraries/{id}/stats response."""

    model_config = ConfigDict(from_attributes=True)

    library_id: int
    series_count: int
    chapter_count: int
    downloaded_chapter_count: int
    total_cbz_bytes: int
