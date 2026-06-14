"""SQLAlchemy 2.0 ORM models for MangaSama.

All tables use the same conventions:
- Integer PKs (autoincrement for top-level entities)
- `DateTime(timezone=True)` for all timestamps (UTC, always)
- `JSON` columns for lists/dicts (SQLite stores as TEXT; SQLAlchemy serialises)
- Foreign keys use `ondelete="CASCADE"` for parent→child deletes
- All `id` columns are named `id`
- All FK columns are named `<singular_target>_id`

Tables: 12.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    """UTC now — single source of truth for timestamp defaults."""
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------------
# Library
# ----------------------------------------------------------------------------


class Library(Base):
    """A library = a folder on disk, with its own content type and providers.

    Examples:
        - "Manga IT" /data/manga_it (manga, mangaworld+mangaeden+mangadex)
        - "Manhwa"   /data/manhwa    (manhwa, mangadex)
    """

    __tablename__ = "libraries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # manga|manhua|manhwa
    root_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    folder_strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    cover_strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="series_first")

    # Ordered list of provider names; first wins.
    providers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    italian_priority: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    follow_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    jpg_quality: Mapped[int] = mapped_column(Integer, nullable=False, default=85)

    # Soft delete: keep the row, mark deleted, keep data on disk.
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    series: Mapped[list["Series"]] = relationship(
        back_populates="library", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (Index("ix_libraries_type", "type"),)


# ----------------------------------------------------------------------------
# Series
# ----------------------------------------------------------------------------


class Series(Base):
    """A series (manga) belonging to a library."""

    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    alt_titles: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # ongoing|completed|hiatus|cancelled|unknown
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)  # BCP-47

    cover_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Overrides library.providers for this series.
    source_priority: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    followed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    followed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    library: Mapped[Library] = relationship(back_populates="series")
    external_ids: Mapped[list["SeriesExternalId"]] = relationship(
        back_populates="series", cascade="all, delete-orphan", passive_deletes=True
    )
    genres: Mapped[list["SeriesGenre"]] = relationship(
        back_populates="series", cascade="all, delete-orphan", passive_deletes=True
    )
    tags: Mapped[list["SeriesTag"]] = relationship(
        back_populates="series", cascade="all, delete-orphan", passive_deletes=True
    )
    authors: Mapped[list["SeriesAuthor"]] = relationship(
        back_populates="series", cascade="all, delete-orphan", passive_deletes=True
    )
    volumes: Mapped[list["Volume"]] = relationship(
        back_populates="series", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_series_library_id", "library_id"),
        Index("ix_series_library_sort", "library_id", "sort_title"),
        Index("ix_series_followed", "followed"),
    )


# ----------------------------------------------------------------------------
# Series auxiliary tables
# ----------------------------------------------------------------------------


class SeriesExternalId(Base):
    """Maps a Series to its external IDs on each provider (e.g. MAL, AniList, MangaDex)."""

    __tablename__ = "series_external_ids"

    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    series: Mapped[Series] = relationship(back_populates="external_ids")

    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_provider_external_id"),)


class SeriesGenre(Base):
    __tablename__ = "series_genres"

    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), primary_key=True
    )
    genre: Mapped[str] = mapped_column(String(64), primary_key=True)

    series: Mapped[Series] = relationship(back_populates="genres")


class SeriesTag(Base):
    __tablename__ = "series_tags"

    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(64), primary_key=True)

    series: Mapped[Series] = relationship(back_populates="tags")


class SeriesAuthor(Base):
    __tablename__ = "series_authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    # writer|penciller|inker|colorist|letterer|cover_artist|translator
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    series: Mapped[Series] = relationship(back_populates="authors")

    __table_args__ = (
        UniqueConstraint("series_id", "role", "name", name="uq_series_author"),
        Index("ix_authors_role_name", "role", "name"),
    )


# ----------------------------------------------------------------------------
# Volume + Chapter + Page
# ----------------------------------------------------------------------------


class Volume(Base):
    """A volume (or 'book') of a series. May contain one or more chapters."""

    __tablename__ = "volumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False
    )

    number: Mapped[str] = mapped_column(String(16), nullable=False)  # "1", "1.5", "0"
    sort: Mapped[float] = mapped_column(Float, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    cover_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    release_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    series: Mapped[Series] = relationship(back_populates="volumes")
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="volume", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("series_id", "number", "language", name="uq_volume_number_lang"),
        Index("ix_volumes_series_sort", "series_id", "sort"),
    )


class Chapter(Base):
    """A single chapter of a volume.

    The `source_provider + source_id + language` triple is the idempotency key:
    a chapter downloaded twice is the same row.
    """

    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    volume_id: Mapped[int] = mapped_column(
        ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False
    )

    number: Mapped[str] = mapped_column(String(16), nullable=False)
    sort: Mapped[float] = mapped_column(Float, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    source_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)  # BCP-47

    pages_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    cbz_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    cbz_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    comic_info_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    volume: Mapped[Volume] = relationship(back_populates="chapters")
    pages: Mapped[list["Page"]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint(
            "source_provider", "source_id", "language", name="uq_chapter_source_lang"
        ),
        Index("ix_chapters_volume_sort", "volume_id", "sort"),
        Index("ix_chapters_downloaded_at", "downloaded_at"),
        Index("ix_chapters_language", "language"),
    )


class Page(Base):
    """A single page within a chapter."""

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )

    index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-based
    filename: Mapped[str] = mapped_column(String(32), nullable=False)  # page001.jpg
    source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    chapter: Mapped[Chapter] = relationship(back_populates="pages")

    __table_args__ = (UniqueConstraint("chapter_id", "index", name="uq_chapter_page"),)


# ----------------------------------------------------------------------------
# Follow / Jobs / Domain health
# ----------------------------------------------------------------------------


class FollowLog(Base):
    """Audit trail for follow-scheduler runs."""

    __tablename__ = "follow_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False
    )

    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    new_chapters_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ok|error|partial
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (Index("ix_follow_log_series_time", "series_id", "checked_at"),)


class ProviderJob(Base):
    """Background job (download, scrape, metadata refresh, ...)."""

    __tablename__ = "provider_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # scrape_chapter|scrape_series|download|pack_cbz|metadata_enrich|health_check
    provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # pending|running|done|error
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_jobs_status_started", "status", "started_at"),
        Index("ix_jobs_type_provider", "job_type", "provider"),
    )


class DomainHealth(Base):
    """Health tracking for each (source, domain) pair.

    Populated from config/sources.yaml on startup; updated by the cron.
    """

    __tablename__ = "domain_health"

    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    domain: Mapped[str] = mapped_column(String(256), primary_key=True)

    last_ok: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fail: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    healthy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    __table_args__ = (Index("ix_domain_health_source_healthy", "source", "healthy"),)
