"""Job schemas — read-only DTOs for the `provider_jobs` table.

The full job queue/streaming is implemented in step 12; for now we only
need the read shape so future endpoints can compile."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    provider: str | None = None
    status: str
    progress: int = 0
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
