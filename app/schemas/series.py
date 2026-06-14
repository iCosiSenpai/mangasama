"""Series schemas — request/response DTOs for the `series` + `series_external_ids` tables."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SeriesExternalIdRead(BaseModel):
    """One row from `series_external_ids`."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    external_id: str
    url: str | None = None
    fetched_at: datetime | None = None


class SeriesAuthorRead(BaseModel):
    """One row from `series_authors`."""

    model_config = ConfigDict(from_attributes=True)

    role: str
    name: str


class SeriesRead(BaseModel):
    """Full series detail. Returned by GET /series/{id} and POST /series."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    library_id: int
    title: str
    sort_title: str | None = None
    alt_titles: list[str] = Field(default_factory=list)
    status: str | None = None
    summary: str | None = None
    year: int | None = None
    language: str | None = None
    cover_path: str | None = None
    source_priority: list[str] = Field(default_factory=list)
    followed: bool = False
    followed_at: datetime | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deleted: bool = False
    # Relationships
    external_ids: list[SeriesExternalIdRead] = Field(default_factory=list)
    authors: list[SeriesAuthorRead] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    volume_count: int = 0


class SeriesListItem(BaseModel):
    """Lighter payload for list endpoints — avoids fetching full relationship graph."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    library_id: int
    title: str
    sort_title: str | None = None
    year: int | None = None
    status: str | None = None
    cover_path: str | None = None
    language: str | None = None
    followed: bool = False
    external_ids: list[SeriesExternalIdRead] = Field(default_factory=list)


class SeriesCreate(BaseModel):
    """Body for `POST /api/series`. We add a series that exists on a remote source."""

    library_id: int = Field(..., ge=1)
    provider: str = Field(..., min_length=1, max_length=32)
    external_id: str = Field(..., min_length=1, max_length=256)
    language: str | None = "it"
    run_metadata_refresh: bool = True


class SeriesUpdate(BaseModel):
    """Body for `PATCH /api/series/{id}`. None = don't touch."""

    model_config = ConfigDict(from_attributes=True)

    title: str | None = Field(default=None, min_length=1, max_length=500)
    sort_title: str | None = Field(default=None, max_length=500)
    alt_titles: list[str] | None = None
    status: str | None = Field(default=None, max_length=32)
    summary: str | None = None
    year: int | None = None
    language: str | None = Field(default=None, max_length=8)
    cover_path: str | None = Field(default=None, max_length=1024)
    source_priority: list[str] | None = None
    followed: bool | None = None


class SeriesMetadataRefreshRequest(BaseModel):
    """Body for `POST /api/series/{id}/metadata/refresh`."""

    providers: list[str] | None = None
    download_cover: bool = True


class SeriesMetadataRefreshResult(BaseModel):
    """Response for `POST /api/series/{id}/metadata/refresh`."""

    model_config = ConfigDict(from_attributes=True)

    series: SeriesRead
    # The full `MergedMetadata.to_dict()` payload — includes attribution,
    # sources, and all merged fields.
    merged: dict
    cover_cached: bool
    sources_used: list[str] = Field(default_factory=list)
