"""Follow schemas — summary of a followed series + its last check."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FollowSummary(BaseModel):
    """A followed series with the outcome of its most recent follow check."""

    series_id: int
    library_id: int
    title: str
    followed_at: datetime | None = None
    last_checked_at: datetime | None = None
    last_status: str | None = None
    last_new_chapters: int | None = None
