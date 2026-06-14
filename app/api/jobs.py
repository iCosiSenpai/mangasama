"""`/api/jobs` — background job log + live SSE feed.

Reads the `provider_jobs` rows written by the download workers and
exposes a Server-Sent-Events stream fed by the in-process job event bus
(`app/services/job_events.py`).
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.deps import DBSession
from app.models.orm import ProviderJob
from app.schemas.job import JobRead
from app.services.job_events import get_job_event_bus

router = APIRouter(tags=["jobs"])

#: Seconds between SSE keepalive comments when no events arrive.
_KEEPALIVE_SECONDS = 15.0


@router.get("/jobs", response_model=list[JobRead])
async def list_jobs(
    session: DBSession,
    status: str | None = Query(default=None, max_length=16),
    job_type: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[JobRead]:
    stmt = select(ProviderJob)
    if status is not None:
        stmt = stmt.where(ProviderJob.status == status)
    if job_type is not None:
        stmt = stmt.where(ProviderJob.job_type == job_type)
    stmt = stmt.order_by(ProviderJob.id.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [JobRead.model_validate(r) for r in rows]


async def job_event_stream(keepalive: float = _KEEPALIVE_SECONDS):
    """SSE body generator: subscribe to the job bus and yield frames.

    Module-level (not a closure) so it can be unit-tested directly without
    driving an HTTP stream.
    """
    bus = get_job_event_bus()
    async with bus.subscribe() as queue:
        yield ": connected\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=keepalive)
                yield f"data: {json.dumps(event)}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"


@router.get("/jobs/stream")
async def stream_jobs() -> StreamingResponse:
    """Server-Sent-Events feed of job state changes (running/done/error)."""
    return StreamingResponse(
        job_event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(job_id: int, session: DBSession) -> JobRead:
    row = (
        await session.execute(select(ProviderJob).where(ProviderJob.id == job_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    return JobRead.model_validate(row)
