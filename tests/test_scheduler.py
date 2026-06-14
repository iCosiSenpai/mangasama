"""Tests for the APScheduler wiring (`app/scheduler/jobs.py`)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.db.session import session_scope
from app.models.orm import ProviderJob
from app.scheduler import jobs


@pytest.fixture(autouse=True)
def _reset_scheduler():
    jobs.reset_for_tests()
    yield
    jobs.reset_for_tests()


@pytest.mark.asyncio
async def test_start_scheduler_registers_jobs():
    jobs.start_scheduler()
    try:
        sched = jobs.get_scheduler()
        assert sched is not None
        ids = {j.id for j in sched.get_jobs()}
        assert {"follow_check", "cleanup_jobs", "domain_health"} <= ids
    finally:
        jobs.stop_scheduler()
    assert jobs.get_scheduler() is None


@pytest.mark.asyncio
async def test_cleanup_deletes_old_provider_jobs():
    now = datetime.now(timezone.utc)
    async with session_scope() as s:
        s.add(ProviderJob(
            job_type="download", status="done", finished_at=now - timedelta(days=60),
        ))
        s.add(ProviderJob(
            job_type="download", status="done", finished_at=now - timedelta(days=1),
        ))

    await jobs._run_cleanup()

    async with session_scope() as s:
        remaining = (await s.execute(select(func.count(ProviderJob.id)))).scalar_one()
    assert remaining == 1  # only the recent job survives the 30-day retention


@pytest.mark.asyncio
async def test_follow_check_runs_with_no_due_series():
    # No followed series → no-op, must not raise.
    await jobs._run_follow_check()
