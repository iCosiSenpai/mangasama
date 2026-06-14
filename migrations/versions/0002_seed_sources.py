"""Seed domain_health from config/sources.yaml.

Revision ID: 0002_seed_sources
Revises: 0001_initial
Create Date: 2026-06-10

For each source in `config/sources.yaml`:
  - Insert one (source, domain) row in `domain_health` for the primary
  - Insert one row for each alternate domain
  - All start `healthy=True, fail_count=0`

This migration is **idempotent**: if the row already exists, the INSERT
is a no-op. The same rows are also re-seeded on every app startup (see
`app/services/health.py` / `app/db/init.py`) so the YAML is the source of
truth — the migration is just the bootstrap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
import yaml
from alembic import op

revision: str = "0002_seed_sources"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _load_sources_yaml() -> dict:
    """Read sources.yaml relative to the project root.

    We resolve relative to the alembic config / cwd. In Docker the
    container's CWD is /app, so the path is /app/config/sources.yaml.
    In local dev it depends on where alembic is invoked from — we look
    in `config/sources.yaml` first, then `../config/sources.yaml` (in
    case alembic runs from inside the project root and the path is
    resolved differently).
    """
    candidates = [
        Path.cwd() / "config" / "sources.yaml",
        Path(__file__).resolve().parent.parent.parent / "config" / "sources.yaml",
    ]
    for p in candidates:
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("sources") or {}
    return {}


def upgrade() -> None:
    sources = _load_sources_yaml()
    if not sources:
        # Nothing to do — sources.yaml missing or empty. The app will
        # surface this later via /api/health.
        return

    rows: list[dict] = []
    for source_name, cfg in sources.items():
        if not cfg.get("enabled", True):
            continue
        primary = cfg.get("primary")
        if primary:
            rows.append({"source": source_name, "domain": primary})
        for alt in cfg.get("alternates") or []:
            rows.append({"source": source_name, "domain": alt})

    if not rows:
        return

    # Use the dialect's INSERT...ON CONFLICT for cross-DB compatibility.
    # For SQLite, this is "INSERT OR IGNORE".
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    insert_prefix = "INSERT OR IGNORE" if is_sqlite else "INSERT IGNORE"
    # Postgres / MySQL: explicit ON CONFLICT (PK) DO NOTHING is more
    # portable. Use the SQLAlchemy core insert with dialect-aware handling.

    table = sa.table(
        "domain_health",
        sa.column("source", sa.String),
        sa.column("domain", sa.String),
        sa.column("healthy", sa.Boolean),
        sa.column("fail_count", sa.Integer),
    )

    if is_sqlite:
        op.execute(
            table.insert().prefix_with("OR IGNORE").values(
                [{"source": r["source"], "domain": r["domain"], "healthy": True, "fail_count": 0}
                 for r in rows]
            )
        )
    else:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.mysql import insert as mysql_insert

        if bind.dialect.name == "postgresql":
            stmt = pg_insert(table).values(
                [{"source": r["source"], "domain": r["domain"], "healthy": True, "fail_count": 0}
                 for r in rows]
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=["source", "domain"])
            op.execute(stmt)
        elif bind.dialect.name == "mysql":
            stmt = mysql_insert(table).values(
                [{"source": r["source"], "domain": r["domain"], "healthy": True, "fail_count": 0}
                 for r in rows]
            )
            stmt = stmt.on_duplicate_key_update(healthy=stmt.inserted.healthy)
            op.execute(stmt)
        else:
            # Fallback: plain insert; unique constraint will fail loudly if
            # rerun, which is the expected behaviour for an unknown dialect.
            op.bulk_insert(table, rows)


def downgrade() -> None:
    """Remove only the rows we inserted, in case the user re-runs.

    We delete by matching against the YAML so we don't wipe rows created
    at runtime by the health-cron.
    """
    sources = _load_sources_yaml()
    if not sources:
        return
    domains: list[tuple[str, str]] = []
    for source_name, cfg in sources.items():
        if cfg.get("primary"):
            domains.append((source_name, cfg["primary"]))
        for alt in cfg.get("alternates") or []:
            domains.append((source_name, alt))
    if not domains:
        return

    bind = op.get_bind()
    table = sa.table(
        "domain_health",
        sa.column("source", sa.String),
        sa.column("domain", sa.String),
        sa.column("fail_count", sa.Integer),
    )
    # Only delete rows that still have fail_count=0 (i.e. untouched by the
    # health-cron since seed). This protects runtime updates.
    for source, domain in domains:
        op.execute(
            sa.delete(table)
            .where(table.c.source == source)
            .where(table.c.domain == domain)
            .where(table.c.fail_count == 0)
        )
