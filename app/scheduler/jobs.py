"""APScheduler jobs — periodic follow checks + job-log cleanup.

Boot order (see `app/main.py` lifespan): the download queue/workers start
first, then `start_scheduler()` registers the interval jobs. Each job
opens its own DB session via `session_scope()` and delegates to the
service layer.

We use the default in-memory job store: every job here is interval-based
and re-registers on boot, so there's nothing worth persisting across
restarts (a `SQLAlchemyJobStore` would only add coroutine-serialization
friction). The live `domain_health` cron is intentionally left to step 15.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete

from app.models.orm import ProviderJob
from app.settings import get_settings

logger = structlog.get_logger("mangasama.scheduler")


# ----------------------------------------------------------------- job bodies


async def _run_follow_check() -> None:
    """Check every due followed series and enqueue new chapters."""
    from app.db.session import session_scope
    from app.services import follow

    async with session_scope() as session:
        result = await follow.check_due_series(session)
    logger.info("scheduler.follow_check", **result)


async def _run_domain_health() -> None:
    """Ping every source domain and update `domain_health` for auto-fallback."""
    from app.services.health import check_all_domains

    result = await check_all_domains()
    logger.info("scheduler.domain_health", **result)


async def _run_backup() -> None:
    """WAL-safe SQLite backup (only registered when BACKUP_ENABLED)."""
    import asyncio

    from app.services.backup import create_backup

    path = await asyncio.to_thread(create_backup)
    logger.info("scheduler.backup", path=str(path))


async def _run_cleanup() -> None:
    """Delete `provider_jobs` finished longer ago than the retention window."""
    from app.db.session import session_scope

    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(days=settings.scheduler_job_retention_days)
    async with session_scope() as session:
        res = await session.execute(
            delete(ProviderJob).where(
                ProviderJob.finished_at.is_not(None),
                ProviderJob.finished_at < cutoff,
            )
        )
    logger.info("scheduler.cleanup", deleted=res.rowcount)


# ----------------------------------------------------------------- lifecycle


_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler


def start_scheduler() -> None:
    """Create + start the scheduler and register the interval jobs.

    Must be called from inside the running event loop (the FastAPI
    lifespan does this).
    """
    global _scheduler
    if _scheduler is not None:
        return
    settings = get_settings()
    sched = AsyncIOScheduler(timezone="UTC")
    sched.add_job(
        _run_follow_check,
        trigger="interval",
        minutes=max(1, settings.scheduler_follow_interval_min),
        id="follow_check",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    sched.add_job(
        _run_cleanup,
        trigger="interval",
        hours=24,
        id="cleanup_jobs",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    sched.add_job(
        _run_domain_health,
        trigger="interval",
        minutes=max(1, settings.scheduler_domain_health_min),
        id="domain_health",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    if settings.backup_enabled:
        sched.add_job(
            _run_backup,
            trigger="interval",
            hours=24,
            id="backup",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
    sched.start()
    _scheduler = sched
    logger.info(
        "scheduler.started",
        follow_interval_min=settings.scheduler_follow_interval_min,
        jobs=[j.id for j in sched.get_jobs()],
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler.stopped")


def reset_for_tests() -> None:
    """Drop the scheduler singleton without waiting (test helper)."""
    global _scheduler
    if _scheduler is not None:
        with contextlib.suppress(Exception):
            _scheduler.shutdown(wait=False)
        _scheduler = None


__all__ = [
    "get_scheduler",
    "reset_for_tests",
    "start_scheduler",
    "stop_scheduler",
]
