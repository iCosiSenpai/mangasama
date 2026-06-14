"""Initial schema: 12 tables, indexes, unique constraints.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-10

Tables in dependency order:
  1. libraries
  2. series (FK -> libraries)
  3. series_external_ids, series_genres, series_tags, series_authors (FK -> series)
  4. volumes (FK -> series)
  5. chapters (FK -> volumes)
  6. pages (FK -> chapters)
  7. follow_log, provider_jobs, domain_health (independent, no parent FKs)

The schema here MUST stay in sync with app/models/orm.py. If you change
one, change the other in the same commit, and add a new migration — never
edit this file after merge.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # libraries
    # -----------------------------------------------------------------------
    op.create_table(
        "libraries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("root_path", sa.String(length=1024), nullable=False),
        sa.Column("folder_strategy", sa.String(length=32), nullable=False),
        sa.Column(
            "cover_strategy", sa.String(length=32), nullable=False, server_default="series_first"
        ),
        sa.Column("providers", sa.JSON(), nullable=False),
        sa.Column(
            "italian_priority", sa.Boolean(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "follow_interval_hours", sa.Integer(), nullable=False, server_default="24"
        ),
        sa.Column("jpg_quality", sa.Integer(), nullable=False, server_default="85"),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index("ix_libraries_type", "libraries", ["type"])

    # -----------------------------------------------------------------------
    # series
    # -----------------------------------------------------------------------
    op.create_table(
        "series",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "library_id",
            sa.Integer(),
            sa.ForeignKey("libraries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("sort_title", sa.String(length=500), nullable=True),
        sa.Column("alt_titles", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("cover_path", sa.String(length=1024), nullable=True),
        sa.Column("source_priority", sa.JSON(), nullable=False),
        sa.Column("followed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("followed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index("ix_series_library_id", "series", ["library_id"])
    op.create_index("ix_series_library_sort", "series", ["library_id", "sort_title"])
    op.create_index("ix_series_followed", "series", ["followed"])

    # -----------------------------------------------------------------------
    # series_external_ids  (composite PK)
    # -----------------------------------------------------------------------
    op.create_table(
        "series_external_ids",
        sa.Column(
            "series_id",
            sa.Integer(),
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("provider", sa.String(length=32), primary_key=True),
        sa.Column("external_id", sa.String(length=256), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "external_id", name="uq_provider_external_id"),
    )

    # -----------------------------------------------------------------------
    # series_genres, series_tags  (composite PK)
    # -----------------------------------------------------------------------
    op.create_table(
        "series_genres",
        sa.Column(
            "series_id",
            sa.Integer(),
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("genre", sa.String(length=64), primary_key=True),
    )
    op.create_table(
        "series_tags",
        sa.Column(
            "series_id",
            sa.Integer(),
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tag", sa.String(length=64), primary_key=True),
    )

    # -----------------------------------------------------------------------
    # series_authors
    # -----------------------------------------------------------------------
    op.create_table(
        "series_authors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "series_id",
            sa.Integer(),
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.UniqueConstraint("series_id", "role", "name", name="uq_series_author"),
    )
    op.create_index("ix_authors_role_name", "series_authors", ["role", "name"])

    # -----------------------------------------------------------------------
    # volumes
    # -----------------------------------------------------------------------
    op.create_table(
        "volumes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "series_id",
            sa.Integer(),
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.String(length=16), nullable=False),
        sa.Column("sort", sa.Float(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("cover_path", sa.String(length=1024), nullable=True),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("publisher", sa.String(length=200), nullable=True),
        sa.UniqueConstraint(
            "series_id", "number", "language", name="uq_volume_number_lang"
        ),
    )
    op.create_index("ix_volumes_series_sort", "volumes", ["series_id", "sort"])

    # -----------------------------------------------------------------------
    # chapters  (the critical one: source_provider+source_id+language is the
    # idempotency key for the download orchestrator)
    # -----------------------------------------------------------------------
    op.create_table(
        "chapters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "volume_id",
            sa.Integer(),
            sa.ForeignKey("volumes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.String(length=16), nullable=False),
        sa.Column("sort", sa.Float(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("source_provider", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=256), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("pages_count", sa.Integer(), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("cbz_size", sa.BigInteger(), nullable=True),
        sa.Column("cbz_sha256", sa.String(length=64), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comic_info_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.UniqueConstraint(
            "source_provider", "source_id", "language", name="uq_chapter_source_lang"
        ),
    )
    op.create_index("ix_chapters_volume_sort", "chapters", ["volume_id", "sort"])
    op.create_index("ix_chapters_downloaded_at", "chapters", ["downloaded_at"])
    op.create_index("ix_chapters_language", "chapters", ["language"])

    # -----------------------------------------------------------------------
    # pages
    # -----------------------------------------------------------------------
    op.create_table(
        "pages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "chapter_id",
            sa.Integer(),
            sa.ForeignKey("chapters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("chapter_id", "index", name="uq_chapter_page"),
    )

    # -----------------------------------------------------------------------
    # follow_log, provider_jobs, domain_health  (no parent FKs)
    # -----------------------------------------------------------------------
    op.create_table(
        "follow_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "series_id",
            sa.Integer(),
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("new_chapters_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.create_index("ix_follow_log_series_time", "follow_log", ["series_id", "checked_at"])

    op.create_table(
        "provider_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_jobs_status_started", "provider_jobs", ["status", "started_at"])
    op.create_index("ix_jobs_type_provider", "provider_jobs", ["job_type", "provider"])

    op.create_table(
        "domain_health",
        sa.Column("source", sa.String(length=32), primary_key=True),
        sa.Column("domain", sa.String(length=256), primary_key=True),
        sa.Column("last_ok", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fail", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("healthy", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_domain_health_source_healthy", "domain_health", ["source", "healthy"])


def downgrade() -> None:
    # Reverse order.
    op.drop_index("ix_domain_health_source_healthy", table_name="domain_health")
    op.drop_table("domain_health")

    op.drop_index("ix_jobs_type_provider", table_name="provider_jobs")
    op.drop_index("ix_jobs_status_started", table_name="provider_jobs")
    op.drop_table("provider_jobs")

    op.drop_index("ix_follow_log_series_time", table_name="follow_log")
    op.drop_table("follow_log")

    op.drop_table("pages")

    op.drop_index("ix_chapters_language", table_name="chapters")
    op.drop_index("ix_chapters_downloaded_at", table_name="chapters")
    op.drop_index("ix_chapters_volume_sort", table_name="chapters")
    op.drop_table("chapters")

    op.drop_index("ix_volumes_series_sort", table_name="volumes")
    op.drop_table("volumes")

    op.drop_index("ix_authors_role_name", table_name="series_authors")
    op.drop_table("series_authors")

    op.drop_table("series_tags")
    op.drop_table("series_genres")
    op.drop_table("series_external_ids")

    op.drop_index("ix_series_followed", table_name="series")
    op.drop_index("ix_series_library_sort", table_name="series")
    op.drop_index("ix_series_library_id", table_name="series")
    op.drop_table("series")

    op.drop_index("ix_libraries_type", table_name="libraries")
    op.drop_table("libraries")
